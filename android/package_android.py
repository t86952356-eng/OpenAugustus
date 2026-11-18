#!/usr/bin/env python3
"""
OpenAugustus Android packager (b4.20.4).

Takes the full desktop build (dist/Augustus-source-development.jar) produced
by build.py and produces the slim Android client jar.

Size reduction (unchanged since b4.20.3 - duplicated payloads only, no game
class, module, HUD element or visual/audio asset is removed):

  1. data/resources.bin  (~80 MB)  - byte-identical duplicate of
     loader/resources.jar. The runtime map is now built from the jar
     (see nick/Data.java). REMOVED.
  2. loader/resources.jar editable entries (~66 MB) - the 1,007 assets that
     are also shipped at the jar root and re-applied over the map by
     nick/EditableResources.mergeInto() at every boot. STRIPPED from the jar.
  3. data/cache.bin overlay-covered entries (~43 MB) - every cache entry whose
     class is present in recovery/compiled-source-overlay.jar is dead weight:
     nick/AugustusClassLoader prefers the embedded overlay (cached.putAll).
     Only entries NOT covered by the overlay survive. GATED.
  4. natives/*.dll (16 Windows DLLs, ~9 MB) - the Android launcher (FCL /
     Pojav family) supplies the lwjgl/openal natives for the device. REMOVED;
     nick/Libraries.java skips missing natives gracefully.

NEW in b4.20.4 - Android bootstrap fixes (verified on linux/JDK 8):

  5. JNIC loader stubs (dev/jnic/rNBrJa/JNICLoader + dev/jnic/aqRLGH/
     JNICLoader) injected at the jar ROOT and into the embedded overlay.
     The original loaders ship Windows-x64-only native payloads and throw
     UnsatisfiedLinkError("Platform not supported: linux/aarch64") in their
     static initializers - the exact crash reported on device for b4.20.3:
         nick.Augustus.main
           -> unsafe.ensureClassInitialized(launcher.41)
             -> launcher.41.<clinit> -> dev.jnic.rNBrJa.JNICLoader.<clinit>
  6. $jnicLoader (and native $jnicClinit) of the protected classes
     no-op'd via ASM (PatchJnic): launcher/41, launcher/44p, launcher/46e,
     launcher/46z, net/40U, net/47R3, net/47Ua, net/47Uj, net/47bj.
     The pure-Java $jnicClinit bodies (ZKM key setup) keep running.
  7. net/47Uj.main (the JNIC-protected game bootstrap) replaced with an
     explicit diagnostic explaining the Windows-x64-only native wall
     (see PatchJnic.DIAG_MESSAGE).
  8. JavaFX 8 marker stubs for launcher.Controller (instantiated during the
     bootstrap handshake): the JRE 8 on Android launchers has no JavaFX and
     Class.getDeclaredFields resolves field types eagerly.

Every deletion/patch is protected by a hard gate; the script exits non-zero
and produces no jar if any assumption is violated.
"""
import argparse
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Class-file introspection (minimal, spec-conformant constant pool walker)
# ---------------------------------------------------------------------------

def _walk_methods(data):
    """Yield (access_flags, name_index, descriptor_index) for every method.

    Used by the post-patch gate to prove that $jnicLoader/$jnicClinit are
    no longer ACC_NATIVE in the patched classes.
    """
    if data[0:4] != b"\xca\xfe\xba\xbe":
        raise ValueError("not a class file")
    cp_count = struct.unpack(">H", data[8:10])[0]
    idx = 10
    tags = [0] * cp_count
    utf8 = {}
    i = 1
    while i < cp_count:
        tag = data[idx]
        idx += 1
        tags[i] = tag
        if tag == 1:
            n = struct.unpack(">H", data[idx:idx + 2])[0]
            idx += 2
            utf8[i] = data[idx:idx + n].decode("utf-8", "replace")
            idx += n
        elif tag == 7:
            idx += 2
        elif tag in (8, 16, 19, 20):
            idx += 2
        elif tag == 15:
            idx += 3
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            idx += 4
        elif tag in (5, 6):
            idx += 8
            i += 1
        else:
            raise ValueError("bad constant pool tag %d" % tag)
        i += 1

    def skip_attributes(pos):
        (n,) = struct.unpack(">H", data[pos:pos + 2])
        pos += 2
        for _ in range(n):
            pos += 2
            (ln,) = struct.unpack(">I", data[pos:pos + 4])
            pos += 4 + ln
        return pos

    pos = idx
    pos += 2  # access_flags
    pos += 2  # this_class
    pos += 2  # super_class
    (icount,) = struct.unpack(">H", data[pos:pos + 2])
    pos += 2 + 2 * icount
    (fcount,) = struct.unpack(">H", data[pos:pos + 2])
    pos += 2
    for _ in range(fcount):
        pos += 6
        pos = skip_attributes(pos)
    (mcount,) = struct.unpack(">H", data[pos:pos + 2])
    pos += 2
    out = []
    for _ in range(mcount):
        acc, ni, di = struct.unpack(">HHH", data[pos:pos + 6])
        pos += 6
        pos = skip_attributes(pos)
        out.append((acc, utf8.get(ni, "?"), utf8.get(di, "?")))
    return out


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


# ---------------------------------------------------------------------------
# Android patch toolchain (stubs + PatchJnic)
# ---------------------------------------------------------------------------

def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="dist/Augustus-source-development.jar")
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", default="dist/android-package-report.json")
    ap.add_argument("--jdk17", required=True,
                    help="JDK 17 home (javac --release 8 + run PatchJnic)")
    ap.add_argument("--asm-cp", required=True,
                    help="classpath of the repo's ASM 9.7.1 jars (lib/asm/*)")
    args = ap.parse_args()

    javac = os.path.join(args.jdk17, "bin", "javac")
    java = os.path.join(args.jdk17, "bin", "java")

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
                stripped_entries.append(name)
                continue
            out.writestr(name, res_jar.read(name))
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
    unresolved = original_cache_keys - set(cache) - overlay_keys
    if unresolved:
        raise SystemExit("cache keys would become unresolvable: %r" % sorted(unresolved)[:5])
    new_cache = serialize_cache_bin(cache)
    print(f"[pack] cache.bin: kept {len(cache)} of {len(original_cache_keys)} entries "
          f"({len(covered)} covered by overlay)")

    # ---- 3. Android patch toolchain ----------------------------------------
    workdir = tempfile.mkdtemp(prefix="augustus_android_")
    try:
        stubs_src = os.path.join(workdir, "stubs-src")
        stubs_cls = os.path.join(workdir, "stubs-cls")
        tool_cls = os.path.join(workdir, "tool-cls")
        for d in (stubs_src, stubs_cls, tool_cls):
            os.makedirs(d, exist_ok=True)

        run([sys.executable, os.path.join(HERE, "jnic_stubs.py"), "--out", stubs_src])

        stub_sources = []
        for root, _dirs, files in os.walk(stubs_src):
            for f in files:
                if f.endswith(".java"):
                    stub_sources.append(os.path.join(root, f))
        if len(stub_sources) < 20:
            raise SystemExit("stub generator produced too few sources")
        run([javac, "--release", "8", "-encoding", "UTF-8",
             "-d", stubs_cls] + stub_sources)
        run([javac, "--release", "8", "-encoding", "UTF-8",
             "-cp", args.asm_cp, "-d", tool_cls,
             os.path.join(HERE, "PatchJnic.java")])
        tool_cp = tool_cls + os.pathsep + args.asm_cp

        stub_class_files = []
        for root, _dirs, files in os.walk(stubs_cls):
            for f in files:
                if f.endswith(".class"):
                    rel = os.path.relpath(os.path.join(root, f), stubs_cls)
                    with open(os.path.join(root, f), "rb") as fh:
                        stub_class_files.append((rel.replace(os.sep, "/"), fh.read()))
        print(f"[pack] compiled {len(stub_class_files)} stub classes")

        # ---- 3a. patch ElectricLauncher.jar --------------------------------
        el_in = os.path.join(workdir, "el-in.jar")
        el_out = os.path.join(workdir, "el-out.jar")
        with open(el_in, "wb") as fh:
            fh.write(src.read("loader/ElectricLauncher.jar"))
        run([java, "-cp", tool_cp, "PatchJnic", el_in, el_out,
             "--noop=launcher/41:$jnicLoader",
             "--noop=launcher/44p:$jnicLoader",
             "--noop=launcher/46e:$jnicLoader",
             "--noop=launcher/46z:$jnicLoader"])
        patched_el = open(el_out, "rb").read()

        # ---- 3b. patch embedded overlay + inject stubs ----------------------
        ov_in = os.path.join(workdir, "ov-in.jar")
        ov_out = os.path.join(workdir, "ov-out.jar")
        with open(ov_in, "wb") as fh:
            fh.write(src.read("recovery/compiled-source-overlay.jar"))
        run([java, "-cp", tool_cp, "PatchJnic", ov_in, ov_out,
             "--diag-main=net/47Uj",
             "--noop=net/47Uj:$jnicLoader,$jnicClinit",
             "--noop=net/40U:$jnicLoader,$jnicClinit",
             "--noop=net/47R3:$jnicLoader,$jnicClinit",
             "--noop=net/47bj:$jnicLoader,$jnicClinit",
             "--noop=net/47Ua:$jnicLoader"])
        ov_buf = io.BytesIO()
        with zipfile.ZipFile(ov_out) as ovp, \
                zipfile.ZipFile(ov_buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as o:
            for info in ovp.infolist():
                o.writestr(info.filename, ovp.read(info.filename))
            for rel, path in stub_class_files:
                o.writestr(rel, path)
        patched_overlay = ov_buf.getvalue()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    # ---- patch verification gates ------------------------------------------
    el_check = zipfile.ZipFile(io.BytesIO(patched_el))
    for cls in ("launcher/41", "launcher/44p", "launcher/46e", "launcher/46z"):
        methods = _walk_methods(el_check.read(cls + ".class"))
        hook = [m for m in methods if m[1] in ("$jnicLoader", "$jnicClinit")]
        if any(m[0] & 0x0100 for m in hook):
            raise SystemExit("gate failed: %s JNIC hook still native" % cls)
    ov_check = zipfile.ZipFile(io.BytesIO(patched_overlay))
    for cls, hooks in (("net/47Uj", ("$jnicLoader", "$jnicClinit")),
                       ("net/40U", ("$jnicLoader", "$jnicClinit")),
                       ("net/47R3", ("$jnicLoader", "$jnicClinit")),
                       ("net/47bj", ("$jnicLoader", "$jnicClinit")),
                       ("net/47Ua", ("$jnicLoader",))):
        methods = _walk_methods(ov_check.read(cls + ".class"))
        named = {m[1]: m[0] for m in methods}
        for hook in hooks:
            if named.get(hook, 0) & 0x0100:
                raise SystemExit("gate failed: %s.%s still native" % (cls, hook))
    for stub in ("dev/jnic/rNBrJa/JNICLoader.class", "dev/jnic/aqRLGH/JNICLoader.class",
                 "javafx/fxml/Initializable.class"):
        if stub not in ov_check.namelist():
            raise SystemExit("gate failed: stub %s missing from overlay" % stub)
    print("[pack] JNIC/JavaFX patch gates passed")

    # ---- 4. assemble the Android jar ----------------------------------------
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
            if name == "loader/ElectricLauncher.jar":
                out.writestr(name, patched_el)
                continue
            if name == "recovery/compiled-source-overlay.jar":
                out.writestr(name, patched_overlay)
                continue
            if name.startswith("natives/"):
                continue  # Windows-only DLLs; launcher provides platform natives
            out.writestr(name, src.read(name))
        # Android safety stubs at the jar root (parent-first visibility for
        # classes defined by the ElectricLauncher URLClassLoader)
        for rel, data in stub_class_files:
            out.writestr(rel, data)

    # ---- verification pass ---------------------------------------------------
    with zipfile.ZipFile(out_path) as check:
        if check.testzip() is not None:
            raise SystemExit("CRC check failed on output jar")
        post = set(check.namelist())
        if "data/resources.bin" in post or any(n.startswith("natives/") for n in post):
            raise SystemExit("exclusion verification failed")
        if "loader/resources.jar" not in post or "data/cache.bin" not in post:
            raise SystemExit("payload verification failed")
        for cls in ("472g.class", "47eJ.class", "47Ua.class", "47cq.class"):
            if cls not in post:
                raise SystemExit("missing root patch class " + cls)
        if "assets/augustus/alan/portrait.png" not in post:
            raise SystemExit("missing alan portrait resource")
        rj2 = zipfile.ZipFile(io.BytesIO(check.read("loader/resources.jar")))
        if len(rj2.namelist()) != len(res_jar.namelist()) - len(stripped_entries):
            raise SystemExit("stripped resources.jar entry count mismatch")
        # stubs must exist at the root as well
        for stub in ("dev/jnic/rNBrJa/JNICLoader.class",
                     "dev/jnic/aqRLGH/JNICLoader.class",
                     "javafx/fxml/Initializable.class"):
            if stub not in post:
                raise SystemExit("root stub missing: " + stub)

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
        "android_fixes": {
            "jnic_loader_stubs": ["dev/jnic.rNBrJa.JNICLoader", "dev.jnic.aqRLGH.JNICLoader"],
            "jnic_hook_noop_classes": ["launcher.41", "launcher.44p", "launcher.46e",
                                       "launcher.46z", "net.40U", "net.47R3", "net.47Ua",
                                       "net.47Uj", "net.47bj"],
            "diag_main_class": "net.47Uj",
            "javafx_stub_count": len(stub_class_files) - 2,
        },
    }
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps(report, indent=2))
    print("[pack] ANDROID PACKAGE OK: %s (%.2f MB -> %.2f MB, -%.1f%%)" % (
        out_path, size_before / 1048576, size_after / 1048576, report["reduction_percent"]))


if __name__ == "__main__":
    main()
