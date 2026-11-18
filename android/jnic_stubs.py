#!/usr/bin/env python3
"""Generate the Android safety-stub sources for the OpenAugustus port.

Single source of truth for every stub class the Android jar injects:

  1. dev.jnic.rNBrJa.JNICLoader  - launcher-side JNIC runtime loader
     (referenced by launcher.41/44p/46e/46z static blocks). The original
     throws UnsatisfiedLinkError("Platform not supported: linux/aarch64")
     in its <clinit> because its embedded payload is Windows x64 only.
  2. dev.jnic.aqRLGH.JNICLoader  - client-side JNIC runtime loader used by
     the protected core (net.40U/47R3/47Ua/47Uj/47bj). Same Windows-only
     platform check; delivered as an encrypted classes.bin payload.
  3. javafx.fxml.Initializable + the JavaFX types referenced by
     launcher.Controller (instantiated during the bootstrap handshake).
     The ZKM sealed-field machinery resolves every declared field type
     eagerly (Class.getDeclaredFields), so absent types abort the boot
     with NoClassDefFoundError. The JRE 8 shipped by Android launchers
     (FCL / Pojav family) has no JavaFX at all.

Deliberately NOT stubbed: javafx.scene.media.* - net.47TB
(client.util.AudioClipPlayer) probes for javafx.scene.media.AudioClip via
Class.forName and degrades the music player to a safe no-op when it is
absent; a stub would defeat that detection.

Every stub is compiled with --release 8 and injected BOTH at the jar root
(parent-first visibility for classes defined by the ElectricLauncher
URLClassLoader) AND into recovery/compiled-source-overlay.jar (visibility
for classes defined by AugustusClassLoader, whose lookup order is
cached -> classes.bin -> delegate with no parent delegation).
"""
import argparse
import os

STUBS = {
    "dev/jnic/rNBrJa/JNICLoader.java": """package dev.jnic.rNBrJa;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/**
 * Android-safe replacement for the JNIC runtime loader shipped inside
 * loader/ElectricLauncher.jar.
 *
 * The original loader performs a hard platform check in its static
 * initializer (Windows x86_64/amd64 ONLY, byte range 0..1146368 of the
 * embedded .dat payload) and throws
 * UnsatisfiedLinkError("Platform not supported: " + os + "/" + arch) on
 * every other platform - including Android (linux/aarch64) - which killed
 * the client during bootstrap:
 *
 *   nick.Augustus.main
 *     -> unsafe.ensureClassInitialized(launcher.41)
 *       -> launcher.41.<clinit> -> JNICLoader.<clinit>
 *          -> "Platform not supported: linux/aarch64"
 *
 * This replacement is intentionally minimal and self-contained: it must
 * not reference the obfuscated LZMA helper classes of the original package
 * (dev.jnic.rNBrJa.t / b / C / W ...) because those are only defined
 * inside ElectricLauncher.jar and would not resolve through the
 * application class loader that defines this stub.
 *
 *   - static ByteBuffer z stays allocated (structural parity; nothing
 *     reads it because no native payload is ever loaded),
 *   - init() remains a no-op (the original method body is empty),
 *   - the static initializer NEVER throws and NEVER attempts to extract
 *     or load a native payload: on Android the launcher (FCL / Pojav
 *     family) supplies every native library the game actually needs
 *     (lwjgl, openal).
 */
public class JNICLoader {

    public static ByteBuffer z;

    private String version = "3.7.0";

    public static void init() {
    }

    static {
        z = ByteBuffer.allocateDirect(64);
        z.order(ByteOrder.LITTLE_ENDIAN);
    }
}
""",
    "dev/jnic/aqRLGH/JNICLoader.java": """package dev.jnic.aqRLGH;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/**
 * Android-safe replacement for the second JNIC runtime loader (package
 * dev.jnic.aqRLGH) used by the protected client-core classes
 * (net.40U, net.47R3, net.47Ua, net.47Uj, net.47bj) that ship as original
 * protected bytecode inside the embedded source overlay.
 *
 * Every one of those classes has the static block
 *
 *     static { JNICLoader.init(); X.$jnicLoader(); X.$jnicClinit(); }
 *
 * and the ORIGINAL aqRLGH loader (delivered as an encrypted payload
 * inside data/classes.bin, decrypted by the delegate launcher.444 at
 * runtime) supports Windows x86_64 only - on Android its static
 * initializer would throw UnsatisfiedLinkError the moment the client
 * core is first touched.
 *
 * This stub keeps the public surface those classes use (the static
 * init() no-op plus the shared ByteBuffer) and never throws.
 */
public class JNICLoader {

    public static ByteBuffer z;

    private String version = "3.7.0";

    public static void init() {
    }

    static {
        z = ByteBuffer.allocateDirect(64);
        z.order(ByteOrder.LITTLE_ENDIAN);
    }
}
""",
}

# JavaFX surface referenced by launcher.Controller (fields + method
# signatures). kind is "class" or "interface".
JAVAFX_STUBS = {
    "javafx/fxml/Initializable": "interface",
    "javafx/animation/KeyFrame": "class",
    "javafx/animation/KeyValue": "class",
    "javafx/animation/Timeline": "class",
    "javafx/collections/ObservableList": "interface",
    "javafx/event/ActionEvent": "class",
    "javafx/scene/control/Button": "class",
    "javafx/scene/control/CheckBox": "class",
    "javafx/scene/control/ListView": "class",
    "javafx/scene/control/MultipleSelectionModel": "class",
    "javafx/scene/control/PasswordField": "class",
    "javafx/scene/control/TabPane": "class",
    "javafx/scene/control/TextField": "class",
    "javafx/scene/input/MouseEvent": "class",
    "javafx/scene/layout/AnchorPane": "class",
    "javafx/scene/paint/Paint": "class",
    "javafx/scene/text/Text": "class",
    "javafx/util/Duration": "class",
}

JAVAFX_DOC = """/**
 * Android-safe empty stub (JavaFX 8 is absent from the JRE 8 used by
 * Android launchers). launcher.Controller - instantiated once during the
 * headless bootstrap handshake - references this type in its fields or
 * method signatures, and the ZKM sealed-field machinery resolves every
 * declared field type eagerly (Class.getDeclaredFields ->
 * NoClassDefFoundError otherwise). No method of the real JavaFX API is
 * ever invoked on the game boot path.
 */
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output source directory")
    args = ap.parse_args()

    written = []
    for rel, body in STUBS.items():
        path = os.path.join(args.out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        written.append(rel)

    for internal, kind in sorted(JAVAFX_STUBS.items()):
        pkg, name = internal.rsplit("/", 1)
        path = os.path.join(args.out, internal.replace("/", os.sep), name + ".java")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("package %s;\n\n%spublic %s %s {\n}\n" % (
                pkg.replace("/", "."), JAVAFX_DOC, kind, name))
        written.append(internal + ".java")

    print("[stubs] generated %d stub sources -> %s" % (len(written), args.out))
    for rel in written:
        print("   ", rel)


if __name__ == "__main__":
    main()
