#!/usr/bin/env python3
"""
Generates OpenAugustus-Android-<ver>.json - a standalone Minecraft "Client
Version" manifest for Android launchers (Fold Craft Launcher / Zalith /
Pojav family), following the exact same proven pattern as the SigmaNG-Android
manifest.

Design notes (FCL/Pojav backend compatibility, 1.8.9 / LWJGL2 edition):
  * The Pojav/FCL backend requires an "org.lwjgl.lwjgl:lwjgl:2.9.4-..."
    library entry to classify the version as LWJGL2-era and select its
    lwjgl2 compatibility natives. Exactly one such entry is kept (artifact
    only - the client jar ships the LWJGL 2.9.4 Java classes itself inside
    data/classes.bin, exactly like the vanilla 1.8.9 jar layout).
  * The client jar (downloads.client) is a fat jar containing every other
    dependency, all game/client classes and all assets.
  * minecraftArguments / assetIndex / assets / javaVersion are copied from
    the official vanilla 1.8.9 manifest; mainClass is our bootstrapper
    (nick.Augustus, the jar's own Main-Class). The Android guards inside the
    client are automatic (headless/JavaFX detection) - no JVM flag needed.
"""
import argparse
import datetime
import hashlib
import json
import os
import urllib.request

VANILLA_189_URL = ("https://piston-meta.mojang.com/v1/packages/"
                   "d546f1707a3f2b7d034eece5ea2e311eda875787/1.8.9.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", required=True, help="path to OpenAugustus-Android jar")
    ap.add_argument("--client-url", required=True,
                    help="public download URL of the client jar (GitHub release asset)")
    ap.add_argument("--id", default="OpenAugustus-Android")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with urllib.request.urlopen(VANILLA_189_URL, timeout=60) as resp:
        vanilla = json.load(resp)

    with open(args.jar, "rb") as fh:
        data = fh.read()
    sha1 = hashlib.sha1(data).hexdigest()
    size = len(data)

    # Single LWJGL2 entry (version detection only) - keep name + artifact.
    lwjgl_entry = None
    for lib in vanilla["libraries"]:
        if lib["name"].startswith("org.lwjgl.lwjgl:lwjgl:"):
            lwjgl_entry = {
                "name": lib["name"],
                "downloads": {"artifact": lib["downloads"]["artifact"]},
            }
            break
    if lwjgl_entry is None:
        raise SystemExit("vanilla manifest did not contain org.lwjgl.lwjgl:lwjgl")

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    manifest = {
        "id": args.id,
        "type": "release",
        "mainClass": "nick.Augustus",
        "minimumLauncherVersion": vanilla.get("minimumLauncherVersion", 14),
        "javaVersion": vanilla.get("javaVersion", {"component": "jre-legacy", "majorVersion": 8}),
        "assetIndex": vanilla["assetIndex"],
        "assets": vanilla["assets"],
        "complianceLevel": vanilla.get("complianceLevel", 0),
        "downloads": {
            "client": {
                "sha1": sha1,
                "size": size,
                "url": args.client_url,
            }
        },
        "libraries": [lwjgl_entry],
        "minecraftArguments": vanilla["minecraftArguments"],
        "logging": vanilla.get("logging"),
        "releaseTime": now,
        "time": now,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print("wrote", args.out, "- id:", args.id, "- client:", sha1[:12], f"({size:,} bytes)")


if __name__ == "__main__":
    main()
