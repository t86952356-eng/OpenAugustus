package client.util;

import client.Client;
import java.awt.AWTException;
import java.awt.SystemTray;
import java.awt.TrayIcon;
import java.awt.TrayIcon.MessageType;
import java.io.IOException;
import java.util.Objects;
import javax.imageio.ImageIO;

public class SystemTrayNotifier {
   // Android port: system tray notifications are a desktop-only nicety. On headless
   // Android JVMs every AWT tray call throws HeadlessException, which previously escaped
   // updateState()/applyString() as an unchecked crash (e.g. on every module toggle with
   // the OldNotification module enabled). Both paths are now fully guarded.
   public static TrayIcon trayIcon;

   public static void updateState() {
      try {
         if (java.awt.GraphicsEnvironment.isHeadless() || !SystemTray.isSupported()) {
            return;
         }
         trayIcon = new TrayIcon(
            ImageIO.read(
               Objects.requireNonNull(PicturesConfigPngManager.class.getClassLoader().getResourceAsStream("assets/augustus/pictures/logoWindows.png"))
            ),
            "Augustus Message"
         );
      } catch (Throwable throwable) {
         trayIcon = null;
         return;
      }

      try {
         SystemTray systemTray = SystemTray.getSystemTray();
         trayIcon.setImageAutoSize(true);
         trayIcon.setToolTip("Message from " + Client.getClient().getString4() + " hack client");
         systemTray.add(trayIcon);
      } catch (AWTException aWTException) {
      } catch (Throwable throwable) {
         trayIcon = null;
      }
   }

   public static void applyString(String text, String text2) {
      if (trayIcon == null) return;
      try {
         trayIcon.displayMessage(text, text2, MessageType.INFO);
      } catch (Throwable throwable) {
      }
   }
}
