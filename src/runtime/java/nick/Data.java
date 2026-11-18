package nick;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.InflaterInputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/** Reconstructed from the original bytecode; no target classes are invoked here. */
public final class Data {
    public static InputStream decompress(InputStream compressed) throws IOException {
        try (InputStream in = new InflaterInputStream(compressed);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int n;
            while ((n = in.read(buffer)) > 0) out.write(buffer, 0, n);
            return new ByteArrayInputStream(out.toByteArray());
        }
    }
    private static String readString(DataInputStream in) throws Throwable {
        byte[] b = new byte[in.readInt()];
        in.readFully(b);
        return new String(b, StandardCharsets.UTF_8);
    }
    private static char[] readCharArray(DataInputStream in) throws Throwable {
        in.readByte();
        char[] chars = new char[in.readInt()];
        for (int i=0; i<chars.length; i++) {
            byte lo = in.readByte();
            byte hi = in.readByte();
            chars[i] = (char)((hi << 8) | (lo & 255));
        }
        return chars;
    }
    private static byte[] readByteArray(DataInputStream in) throws Throwable {
        byte[] b = new byte[in.readInt()];
        in.readFully(b);
        return b;
    }
    private static InputStream resource(String name) {
        return Objects.requireNonNull(Data.class.getClassLoader().getResourceAsStream(name));
    }
    public static Map<String, byte[]> resources() {
        // Android port: build the resource map from loader/resources.jar (a plain zip whose
        // entries were byte-identical to the old data/resources.bin payload). This removes
        // an ~80 MB duplicate from the client jar without changing any resource the game
        // sees: EditableResources.mergeInto still applies the editable overrides on top.
        try {
            Map<String, byte[]> map = new HashMap<>();
            ZipInputStream in = new ZipInputStream(resource("loader/resources.jar"));
            try {
                ZipEntry entry;
                byte[] buffer = new byte[8192];
                while ((entry = in.getNextEntry()) != null) {
                    if (entry.isDirectory()) continue;
                    ByteArrayOutputStream out = new ByteArrayOutputStream();
                    int n;
                    while ((n = in.read(buffer)) > 0) out.write(buffer, 0, n);
                    map.put(entry.getName(), out.toByteArray());
                }
            } finally {
                in.close();
            }
            EditableResources.mergeInto(map);
            return map;
        } catch (Throwable t) { t.printStackTrace(System.err); return null; }
    }
    public static Map<String, byte[]> classes() {
        try {
            Map<String, byte[]> map = new HashMap<>();
            DataInputStream in = new DataInputStream(decompress(resource("data/classes.bin")));
            while (in.available()>0) map.put(new String(readCharArray(in)), readByteArray(in));
            in.close();
            return map;
        } catch (Throwable t) { t.printStackTrace(System.err); return null; }
    }
    public static Map<String, byte[]> cache() {
        // Android port: the slim Android build strips overlay-covered entries from
        // data/cache.bin; if the payload is absent the (empty) map is still valid because
        // every class then resolves via the embedded overlay or data/classes.bin.
        Map<String, byte[]> map = new HashMap<>();
        InputStream input = Data.class.getClassLoader().getResourceAsStream("data/cache.bin");
        if (input == null) return map;
        try {
            DataInputStream in = new DataInputStream(input);
            while (in.available()>0) map.put(readString(in).replace('/', '.'), readByteArray(in));
            return map;
        } catch (Throwable t) { throw new RuntimeException(t); }
    }
    public static Map<String, byte[]> keys() {
        try {
            Map<String, byte[]> map = new HashMap<>();
            DataInputStream in = new DataInputStream(resource("data/keys.bin"));
            while (in.available()>0) map.put(readString(in).replace('/', '.'), readByteArray(in));
            return map;
        } catch (Throwable t) { throw new RuntimeException(t); }
    }
}
