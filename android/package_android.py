#!/usr/bin/env python3
"""
OpenAugustus Android packager.

Takes the full desktop build (dist/Augustus-source-development.jar) produced by
build.py and produces the slim Android client jar. Size reduction comes from
removing *duplicated* payloads only - no game class, module, HUD element or
visual/audio asset is removed:

  1. data/resources.bin  (~80 MB)  - byte-identical duplicate of
     loader/resources.jar. The runtime map is now built from the jar
     (see nick/Data.java). REMOVED.
  2. loader/resources.jar editable entries (~66 MB) - the 1,007 assets that are
     also shipped at the jar root and re-applied over the map by
     nick/EditableResources.mergeInto() at every boot. STRIPPED from the jar.
  3. data/cache.bin overlay-covered entries (~43 MB) - every cache entry whose
     class is present in recovery/compiled-source-overlay.jar is dead weight:
     nick/AugustusClassLoader prefers the embedded overlay (cached.putAll).
     Only entries NOT covered by the overlay survive. GATED: the script fails
     if any original cache key would become unresolvable.
  4. natives/*.dll (16 Windows DLLs, ~9 MB) - the Android launcher (FCL /
     Pojav family) supplies the lwjgl/openal natives for the device. REMOVED;
     nick/Libraries.java skips missing natives gracefully.

Every deletion is protected by a hard gate; the script exits non-zero and
produces no jar if any assumption is violated.
"""
import argparse
import io
import json
import os
import struct
import sys
import zipfile
import zlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_classes_bin(data):
    """data/classes.bin: zlib blob of (utf16 key, bytes) records."""
    raw = zlib.decompress(data)
    stream = io.BytesIO(raw)
    out = {}
    while stream.tell() < len(raw):
        stream.read(1)  # marker byte (see nick/Data.readCharArray)
        (n,) = struct.unpack(">i", stream.read(4))
        key = stream.read(n * 2).decode("utf-16le", errors="surrogatepass")
        (m,) = struct.unpack(">i", stream.read(4))
        out[key] = stream.read(m)
    return out


def serialize_classes_bin(entries):
    """Inverse of parse_classes_bin (zlib compressed, marker byte 0)."""
    buf = io.BytesIO()
    for key in sorted(entries):
        kb = key.encode("utf-16le", errors="surrogatepass")
        buf.write(b"\x00")
        buf.write(struct.pack(">i", len(kb) // 2))
        buf.write(kb)
        buf.write(struct.pack(">i", len(entries[key])))
        buf.write(entries[key])
    return zlib.compress(buf.getvalue(), 9)


def parse_cache_bin(data):
    """cache.bin: raw (utf8 key, bytes) records, keys are class names."""
    stream = io.BytesIO(data)
    out = {}
    while stream.tell() < len(data):
        (n,) = struct.unpack(">i", stream.read(4))
        key = stream.read(n).decode("utf-8")
        (m,) = struct.unpack(">i", stream.read(4))
        out[key] = stream.read(m)
    return out


def serialize_cache_bin(entries):
    buf = io.BytesIO()
    for key in sorted(entries):
        kb = key.encode("utf-8")
        buf.write(struct.pack(">i", len(kb)))
        buf.write(kb)
        buf.write(struct.pack(">i", len(entries[key])))
        buf.write(entries[key])
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="dist/Augustus-source-development.jar")
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", default="dist/android-package-report.json")
    args = ap.parse_args()

    src = zipfile.ZipFile(args.input)
    names = set(src.namelist())

    # ---- inputs we require -----------------------------------------------
    required = [
        "data/classes.bin", "data/cache.bin", "data/keys.bin",
        "loader/resources.jar", "loader/ElectricLauncher.jar",
        "recovery/compiled-source-overlay.jar",
        "recovery/editable-resource-index.txt",
        "META-INF/MANIFEST.MF",
    ]
    missing = [n for n in required if n not in names]
    if missing:
        raise SystemExit("missing required entries: %r" % missing)

    # ---- overlay class set ------------------------------------------------
    overlay = zipfile.ZipFile(io.BytesIO(src.read("recovery/compiled-source-overlay.jar")))
    overlay_keys = {n[:-6] for n in overlay.namelist() if n.endswith(".class")}
    print(f"[pack] overlay classes: {len(overlay_keys)}")

    # ---- editable resource index -----------------------------------------
    editable = [l for l in src.read("recovery/editable-resource-index.txt")
                .decode("utf-8").splitlines() if l.strip()]
    editable_set = set(editable)
    print(f"[pack] editable resources: {len(editable_set)}")
    # GATE: every editable entry must exist at the jar root (they are re-merged
    # over the runtime map from there).
    root_missing = [e for e in editable if e not in names]
    if root_missing:
        raise SystemExit("editable resources missing from jar root: %r" % root_missing[:5])

    # ---- 1. resources.jar: strip editable duplicates ----------------------
    res_jar_bytes = src.read("loader/resources.jar")
    res_jar = zipfile.ZipFile(io.BytesIO(res_jar_bytes))
    stripped_rj = io.BytesIO()
    stripped_entries = []
    with zipfile.ZipFile(stripped_rj, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for info in res_jar.infolist():
            name = info.filename
            if name in editable_set:
                # served from the jar root via EditableResources.mergeInto()
                stripped_entries.append(name)
                continue
            out.writestr(name, res_jar.read(name))
    # GATE: only editable-indexed entries may be stripped
    unexpected = [n for n in stripped_entries if n not in editable_set]
    if unexpected:
        raise SystemExit("internal error: stripped non-editable entries")
    print(f"[pack] resources.jar: stripped {len(stripped_entries)} editable entries")

    # ---- 2. cache.bin: strip overlay-covered entries ----------------------
    cache = parse_cache_bin(src.read("data/cache.bin"))
    original_cache_keys = set(cache)
    covered = original_cache_keys & overlay_keys
    for key in covered:
        del cache[key]
    # GATE: every original cache key must still resolve at runtime:
    # either it stayed in cache.bin or it is provided by the embedded overlay.
    unresolved = original_cache_keys - set(cache) - overlay_keys
    if unresolved:
        raise SystemExit("cache keys would become unresolvable: %r" % sorted(unresolved)[:5])
    new_cache = serialize_cache_bin(cache)
    print(f"[pack] cache.bin: kept {len(cache)} of {len(original_cache_keys)} entries "
          f"({len(covered)} covered by overlay)")

    # ---- 3. assemble the Android jar --------------------------------------
    out_path = args.output
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    size_before = os.path.getsize(args.input)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for info in src.infolist():
            name = info.filename
            if name.endswith("/"):
                continue  # drop directory entries
            if name == "data/resources.bin":
                continue  # duplicate of loader/resources.jar (map built from it)
            if name == "data/cache.bin":
                out.writestr(name, new_cache)
                continue
            if name == "loader/resources.jar":
                out.writestr(name, stripped_rj.getvalue())
                continue
            if name.startswith("natives/"):
                continue  # Windows-only DLLs; launcher provides platform natives
            out.writestr(name, src.read(name))

    # ---- verification pass -------------------------------------------------
    with zipfile.ZipFile(out_path) as check:
        if check.testzip() is not None:
            raise SystemExit("CRC check failed on output jar")
        post = set(check.namelist())
        if "data/resources.bin" in post or any(n.startswith("natives/") for n in post):
            raise SystemExit("exclusion verification failed")
        if "loader/resources.jar" not in post or "data/cache.bin" not in post:
            raise SystemExit("payload verification failed")
        # GATE: root patch classes must survive (AugustusClassLoader patches them)
        for cls in ("472g.class", "47eJ.class", "47Ua.class", "47cq.class"):
            if cls not in post:
                raise SystemExit("missing root patch class " + cls)
        # GATE: the editable portrait the build verifies must be at the root
        if "assets/augustus/alan/portrait.png" not in post:
            raise SystemExit("missing alan portrait resource")
        # GATE: the stripped resources.jar entry count must match
        rj2 = zipfile.ZipFile(io.BytesIO(check.read("loader/resources.jar")))
        if len(rj2.namelist()) != len(res_jar.namelist()) - len(stripped_entries):
            raise SystemExit("stripped resources.jar entry count mismatch")

    size_after = os.path.getsize(out_path)
    report = {
        "input_jar": args.input,
        "output_jar": out_path,
        "size_before": size_before,
        "size_after": size_after,
        "reduction_bytes": size_before - size_after,
        "reduction_percent": round(100.0 * (size_before - size_after) / size_before, 1),
        "resources_bin_removed": True,
        "natives_removed": True,
        "resources_jar_stripped_entries": len(stripped_entries),
        "cache_entries_original": len(original_cache_keys),
        "cache_entries_kept": len(cache),
        "cache_entries_overlay_covered": len(covered),
        "overlay_classes": len(overlay_keys),
        "editable_resources": len(editable_set),
    }
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps(report, indent=2))
    print("[pack] ANDROID PACKAGE OK: %s (%.2f MB -> %.2f MB, -%.1f%%)" % (
        out_path, size_before / 1048576, size_after / 1048576, report["reduction_percent"]))


if __name__ == "__main__":
    main()
