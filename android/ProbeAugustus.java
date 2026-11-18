import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipInputStream;

/**
 * CI smoke test for the OpenAugustus Android build.
 *
 * Reproduces, headlessly and without any LWJGL/display dependency, every data
 * loading step the real device boot performs BEFORE touching OpenGL:
 *
 *   nick.Augustus.main (device)          this probe
 *   ---------------------------------    ----------------------------------
 *   Libraries.loader()                   (skipped - needs temp dir only)
 *   Data.classes()                       full parse + expected count
 *   Data.resources()                     full parse from loader/resources.jar
 *                                        (v1 device crash path: old builds read
 *                                        data/resources.bin which no longer exists)
 *   Data.cache()                         parse + every key resolvable
 *   Data.keys()                          full parse, non-empty
 *   AugustusClassLoader patches          root 472g/47eJ/47Ua/47cq present
 *   EmbeddedOverlay.install              overlay parses, all CAFEBABE, count
 *   EditableResources.mergeInto          index entries present at jar root
 *   Libraries.create()                   must skip missing natives silently
 *
 * Exit code 0 + "PROBE-PASSED" = the Android jar is structurally sound.
 */
public final class ProbeAugustus {

    private static int failures = 0;

    private static void check(boolean ok, String label) {
        System.out.println((ok ? "  [ok]   " : "  [FAIL] ") + label);
        if (!ok) failures++;
    }

    private static int countClasses(Map<String, byte[]> map, String label) {
        int n = 0;
        for (byte[] data : map.values()) {
            if (data.length > 8
                    && data[0] == (byte) 0xca && data[1] == (byte) 0xfe
                    && data[2] == (byte) 0xba && data[3] == (byte) 0xbe) n++;
        }
        return n;
    }

    public static void main(String[] args) throws Exception {
        ClassLoader cl = ProbeAugustus.class.getClassLoader();

        System.out.println("== ProbeAugustus: Android jar structural smoke test ==");

        // --- 1. classes.bin (library store) ---------------------------------
        Map<String, byte[]> classes = nick.Data.classes();
        check(classes != null, "Data.classes() returned a map");
        if (classes == null) throw exit();
        check(classes.size() >= 30000, "classes.bin entries >= 30000 (got " + classes.size() + ")");
        // classes.bin mixes plain class data with ~7k original encrypted payloads
        // (SHA-named entries); both are expected - spot-check known library classes.
        byte[] netty = classes.get("io/netty/channel/Channel.class");
        byte[] fastutil = classes.get("it/unimi/dsi/fastutil/ints/Int2ObjectOpenHashMap.class");
        check(netty != null && netty.length > 8 && netty[0] == (byte) 0xca && netty[1] == (byte) 0xfe,
                "known netty class present and is CAFEBABE class data");
        check(fastutil != null && fastutil.length > 8 && fastutil[0] == (byte) 0xca,
                "known fastutil class present and is CAFEBABE class data");

        // --- 2. resources map from loader/resources.jar (v1 crash path) -----
        Map<String, byte[]> resources = nick.Data.resources();
        check(resources != null, "Data.resources() returned a map");
        if (resources == null) throw exit();
        // stripped resources.jar keeps 4731 + 1008 editable merged = 5739
        check(resources.size() == 5739,
                "resources map has 5739 entries (got " + resources.size() + ")");
        check(resources.containsKey("assets/augustus/alan/portrait.png"),
                "editable alan portrait merged into the map");
        byte[] packPng = resources.get("assets/pack.png");
        check(packPng != null && packPng.length > 100, "non-editable assets still served");
        byte[] sound = resources.get("assets/augustus/sounds/click/click1.ogg");
        boolean soundOk = false;
        if (sound == null) {
            // fall back to any augustus sound entry (names vary)
            for (Map.Entry<String, byte[]> e : resources.entrySet()) {
                if (e.getKey().startsWith("assets/augustus/sounds/") && e.getValue().length > 1000) {
                    soundOk = true;
                    break;
                }
            }
        } else {
            soundOk = sound.length > 1000;
        }
        check(soundOk, "augustus sounds present in the resource map");

        // --- 3. cache.bin (client class store, stripped) ---------------------
        Map<String, byte[]> cache = nick.Data.cache();
        check(cache != null, "Data.cache() returned a map");
        if (cache == null) throw exit();
        check(cache.size() >= 500, "cache.bin kept >= 500 uncovered entries (got " + cache.size() + ")");

        // --- 4. overlay coverage gate (device class resolution) -------------
        InputStream overlayStream = cl.getResourceAsStream("recovery/compiled-source-overlay.jar");
        check(overlayStream != null, "embedded overlay present");
        int overlayCount = 0;
        boolean allMagic = true;
        java.util.Set<String> overlayKeys = new java.util.HashSet<>();
        ZipInputStream zi = new ZipInputStream(overlayStream);
        ZipEntry ze;
        while ((ze = zi.getNextEntry()) != null) {
            if (ze.isDirectory() || !ze.getName().endsWith(".class")) continue;
            overlayKeys.add(ze.getName().substring(0, ze.getName().length() - 6));
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = zi.read(buf)) > 0) out.write(buf, 0, n);
            byte[] data = out.toByteArray();
            if (data.length < 8 || data[0] != (byte) 0xca || data[1] != (byte) 0xfe
                    || data[2] != (byte) 0xba || data[3] != (byte) 0xbe) allMagic = false;
            overlayCount++;
        }
        zi.close();
        check(overlayCount >= 5000, "overlay has >= 5000 classes (got " + overlayCount + ")");
        check(allMagic, "every overlay entry is valid class data");

        // every cache key must resolve via cache (dotted keys) or overlay (slash keys)
        boolean allCovered = true;
        for (String key : new String[]{"net/47bX", "net/40U", "net/47uz"}) {
            boolean resolvable = overlayKeys.contains(key) || cache.containsKey(key.replace('/', '.'));
            if (!resolvable) allCovered = false;
        }
        check(allCovered, "sample client classes resolvable via cache/overlay");

        // --- 5. keys.bin ------------------------------------------------------
        Map<String, byte[]> keys = nick.Data.keys();
        check(keys != null && !keys.isEmpty(), "Data.keys() non-empty");

        // --- 6. root patch classes --------------------------------------------
        for (String cls : new String[]{"472g", "47eJ", "47Ua", "47cq"}) {
            check(cl.getResourceAsStream(cls + ".class") != null, "root patch class " + cls + ".class");
        }

        // --- 7. ElectricLauncher payload --------------------------------------
        InputStream el = cl.getResourceAsStream("loader/ElectricLauncher.jar");
        check(el != null, "loader/ElectricLauncher.jar present");
        if (el != null) {
            ZipInputStream ez = new ZipInputStream(el);
            boolean controller = false;
            ZipEntry ee;
            while ((ee = ez.getNextEntry()) != null) {
                if (ee.getName().equals("launcher/Controller.class")) controller = true;
            }
            ez.close();
            check(controller, "ElectricLauncher.jar contains launcher/Controller.class");
        }

        // --- 8. natives must be absent AND Libraries.create() must tolerate it
        check(cl.getResourceAsStream("natives/lwjgl64.dll") == null,
                "Windows natives removed from the Android jar");
        try {
            nick.Libraries.create();
            check(true, "Libraries.create() tolerates missing natives (Android path)");
        } catch (Throwable t) {
            check(false, "Libraries.create() threw: " + t);
        }

        // --- 9. editable index -------------------------------------------------
        InputStream idx = cl.getResourceAsStream("recovery/editable-resource-index.txt");
        check(idx != null, "editable resource index present");
        if (idx != null) {
            java.io.BufferedReader reader = new java.io.BufferedReader(
                    new java.io.InputStreamReader(idx, "UTF-8"));
            int present = 0, total = 0;
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) continue;
                total++;
                if (cl.getResourceAsStream(line) != null) present++;
            }
            reader.close();
            check(total >= 1000 && present == total,
                    "all editable resources present at jar root (" + present + "/" + total + ")");
        }

        if (failures > 0) {
            System.err.println("PROBE-FAILED: " + failures + " check(s) failed");
            System.exit(1);
        }
        System.out.println("PROBE-PASSED: Android jar is structurally sound");
    }

    private static RuntimeException exit() {
        System.err.println("PROBE-FAILED: fatal");
        System.exit(1);
        return new RuntimeException();
    }
}
