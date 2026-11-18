import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.JarOutputStream;

/**
 * Surgical bytecode patcher for the OpenAugustus Android port (b4.20.4).
 *
 * All operations are idempotent and structure-preserving; untouched
 * entries are copied byte-identical:
 *
 *  1. --noop=ClassInternalName:methodA,methodB
 *     Replaces the named methods with an empty implementation and clears
 *     the ACC_NATIVE flag. Used exclusively for the JNIC bootstrap hooks
 *     ($jnicLoader / native $jnicClinit) of the protected classes:
 *     without the Windows x64 payload those native methods can never be
 *     bound on Android, and the class initializers would throw
 *     UnsatisfiedLinkError during bootstrap. Native business methods
 *     (net.40U getters, net.47R3 bus operations, ...) are intentionally
 *     left untouched - they still fail loudly if ever invoked.
 *
 *  2. --diag-main=ClassInternalName
 *     Replaces static void main(String[]) of the JNIC-protected game
 *     bootstrap (net.47Uj) with an explicit, bilingual diagnostic that
 *     explains exactly where the Windows-only native wall sits, instead
 *     of an obscure UnsatisfiedLinkError stack trace.
 *
 * Patched classes (launcher side, inside loader/ElectricLauncher.jar):
 *     launcher/41, launcher/44p, launcher/46e, launcher/46z
 *         -> $jnicLoader no-op ($jnicClinit of these four is pure Java
 *            ZKM state setup and keeps running)
 *
 * Patched classes (client side, inside the embedded source overlay):
 *     net/47Uj -> --diag-main + $jnicLoader/$jnicClinit no-op
 *     net/40U, net/47R3, net/47bj -> $jnicLoader/$jnicClinit no-op
 *     net/47Ua -> $jnicLoader no-op ($jnicClinit is Java, keeps running)
 */
public final class PatchJnic {

    public static final String DIAG_MESSAGE =
        "OpenAugustus/Android: the launcher bootstrap chain is fixed in this build, "
        + "but the game bootstrap (net.47Uj.main) and the client core "
        + "(net.40U / net.47R3 / net.47Ua / net.47bj) are JNIC-protected native code "
        + "compiled for Windows x64 only - no linux/aarch64 payload exists, so they "
        + "cannot execute on this platform. Full Android support requires reimplementing "
        + "that native core. See release android-b4.20.4 notes for the technical analysis.";

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("usage: PatchJnic <injar> <outjar> "
                    + "[--noop cls:m1,m2]... [--diag-main cls]");
            System.exit(2);
        }
        Map<String, Set<String>> noops = new HashMap<String, Set<String>>();
        Set<String> diagMain = new HashSet<String>();
        for (int i = 2; i < args.length; i++) {
            String arg = args[i];
            if (arg.startsWith("--noop=")) {
                String[] p = arg.substring(7).split(":", 2);
                Set<String> m = noops.get(p[0]);
                if (m == null) {
                    m = new HashSet<String>();
                    noops.put(p[0], m);
                }
                for (String name : p[1].split(",")) {
                    m.add(name);
                }
            } else if (arg.startsWith("--diag-main=")) {
                diagMain.add(arg.substring(12));
            } else {
                throw new IllegalArgumentException("bad arg: " + arg);
            }
        }

        JarFile jf = new JarFile(args[0]);
        File outFile = new File(args[1]);
        JarOutputStream jos = new JarOutputStream(new FileOutputStream(outFile));
        try {
            Enumeration<JarEntry> e = jf.entries();
            Set<String> written = new HashSet<String>();
            int patched = 0;
            while (e.hasMoreElements()) {
                JarEntry je = e.nextElement();
                String name = je.getName();
                if (!written.add(name)) {
                    continue; // drop duplicates, keep the first entry
                }
                byte[] data = readAll(jf.getInputStream(je));
                if (name.endsWith(".class")) {
                    String cls = name.substring(0, name.length() - 6);
                    Set<String> noop = noops.get(cls);
                    boolean diag = diagMain.contains(cls);
                    if (noop != null || diag) {
                        data = patchClass(data, noop, diag);
                        patched++;
                    }
                }
                JarEntry ne = new JarEntry(name);
                ne.setTime(0L);
                jos.putNextEntry(ne);
                jos.write(data);
            }
            jos.close();
            System.out.println("[patch] " + patched + " class(es) patched -> "
                    + outFile.getName());
        } finally {
            jf.close();
        }
    }

    private static byte[] patchClass(byte[] data, Set<String> noop, boolean diagMain) {
        ClassReader cr = new ClassReader(data);
        ClassWriter cw = new ClassWriter(cr, 0);
        ClassVisitor cv = new ClassVisitor(Opcodes.ASM9, cw) {
            @Override
            public MethodVisitor visitMethod(int access, String name, String desc,
                                             String signature, String[] exceptions) {
                if (noop != null && noop.contains(name)) {
                    MethodVisitor mv = super.visitMethod(access & ~Opcodes.ACC_NATIVE,
                            name, desc, signature, exceptions);
                    mv.visitCode();
                    mv.visitInsn(Opcodes.RETURN);
                    mv.visitMaxs(0, Math.max(1, Type.getArgumentsAndReturnSizes(desc) >> 2));
                    mv.visitEnd();
                    return null;
                }
                if (diagMain && name.equals("main")
                        && desc.equals("([Ljava/lang/String;)V")) {
                    MethodVisitor mv = super.visitMethod(
                            (access & ~Opcodes.ACC_NATIVE) | Opcodes.ACC_STATIC,
                            name, desc, signature, exceptions);
                    // String message = DIAG_MESSAGE;
                    // System.err.println(message);
                    // throw new RuntimeException(message);
                    mv.visitCode();
                    mv.visitLdcInsn(DIAG_MESSAGE);
                    mv.visitVarInsn(Opcodes.ASTORE, 1);
                    mv.visitFieldInsn(Opcodes.GETSTATIC, "java/lang/System", "err",
                            "Ljava/io/PrintStream;");
                    mv.visitVarInsn(Opcodes.ALOAD, 1);
                    mv.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/io/PrintStream",
                            "println", "(Ljava/lang/String;)V", false);
                    mv.visitTypeInsn(Opcodes.NEW, "java/lang/RuntimeException");
                    mv.visitInsn(Opcodes.DUP);
                    mv.visitVarInsn(Opcodes.ALOAD, 1);
                    mv.visitMethodInsn(Opcodes.INVOKESPECIAL, "java/lang/RuntimeException",
                            "<init>", "(Ljava/lang/String;)V", false);
                    mv.visitInsn(Opcodes.ATHROW);
                    mv.visitMaxs(3, 2);
                    mv.visitEnd();
                    return null;
                }
                return super.visitMethod(access, name, desc, signature, exceptions);
            }
        };
        cr.accept(cv, 0);
        return cw.toByteArray();
    }

    private static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) {
            out.write(buf, 0, n);
        }
        in.close();
        return out.toByteArray();
    }

    private PatchJnic() {
    }
}
