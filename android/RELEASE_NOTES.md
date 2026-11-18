# OpenAugustus b4.20.3 — Android Client Version (1.8.9)

نسخة **OpenAugustus** (Augustus b4.20.3 — مصدر نظيف 100% على Minecraft 1.8.9 + OptiFine + Baritone) المعدّلة لتعمل على **أندرويد** عبر **Fold Craft Launcher (FCL)** مع عارض **GL4ES / Holy-GL4ES أو Krypton (NG-GL4ES)** — بنظام **Client Version** مستقل.

- الملفات: `OpenAugustus-Android-b4.20.3.jar` (العميل الكامل) + `OpenAugustus-Android-b4.20.3.json` (ملف الإصدار) + `android-package-report.json` (تقرير التخفيف).
- المصدر: https://github.com/t86952356-eng/OpenAugustus

## الحجم: 347.95 MB ← 171.43 MB (تخفيف 50.7%)

كل التخفيف من **إزالة الازدواجية وحذف ملفات ويندوز فقط** — لم يُحذف أي كلاس لعبة، أو موديول، أو عنصر HUD، أو أي أصل بصري/صوتي:

| العنصر | قبل | بعد | السبب |
|---|---|---|---|
| `data/resources.bin` | 80 MB | 0 | نسخة مطابقة بايت-ببايت من `loader/resources.jar` — الخريطة تُبنى الآن من الجار |
| `loader/resources.jar` (مداخل مكررة) | 84 MB | 17 MB | 1,007 أصل يُشحن أيضاً عند جذر الجار ويُدمج فوق الخريطة في كل إقلاع |
| `data/cache.bin` | 44 MB | 0.6 MB | 3,341 كلاس مغطاة بالـ overlay المدمج (الأولوية للـ overlay وقت التحميل) |
| `natives/*.dll` (16 DLL ويندوز) | 9 MB | 0 | المشغل (FCL) يوفر مكتبات النظام للمنصة |
| ترجمة بدون debug info (`-g:none`) | — | — | تقليل حجم الكلاسات المترجمة |

## حمايات أندرويد المدمجة (تلقائية — بلا أي تغيير بصري)

- **مشغل الموسيقى (JavaFX AudioClip):** Temurin 8 لا يحتوي JavaFX — الآن يتحول لوضع صامت آمن بدل `NoClassDefFoundError`.
- **إشعارات سطح المكتب (SystemTray):** كانت ستكرش عند كل تفعيل موديول مع OldNotification على JVM بلا واجهة — الآن معطلة بأمان.
- **Debug Console (Swing JFrame):** يتحقق من وضع headless قبل فتح أي نافذة.
- **استخراج الـ DLLs:** يتخطى المكتبات الغائبة بأمان (أندرويد بلا DLLs).
- **ClickGUI و HUD والموديولات الـ 237: صفر تعديل.**

## التثبيت على FCL (Fold Craft Launcher)

1. حمّل `OpenAugustus-Android-b4.20.3.jar` و `OpenAugustus-Android-b4.20.3.json`.
2. في مجلد FCL: `files/.minecraft/versions/OpenAugustus-Android-b4.20.3/`
   (أو مسار اللعبة الظاهر في إعدادات FCL — Storage / مسار .minecraft)
   - ضع الجار والـ JSON داخل المجلد **بنفس الاسم**:
     - `versions/OpenAugustus-Android-b4.20.3/OpenAugustus-Android-b4.20.3.jar`
     - `versions/OpenAugustus-Android-b4.20.3/OpenAugustus-Android-b4.20.3.json`
3. شغّل FCL ← الإصدارات ← اختر **OpenAugustus-Android-b4.20.3**.
   - FCL سينزّل أصول Minecraft 1.8.9 الرسمية تلقائياً (assets 1.8) في أول تشغيل.
   - الـ JSON يطلب **Java 8 (jre-legacy)** تلقائياً — لا تحتاج ضبط شيء.
4. العارض: **GL4ES** أو **Holy-GL4ES** (موصى به لـ 1.8.9) — أو Krypton/NG-GL4ES إن كان متاحاً لديك. عارض Zink يعمل أيضاً على أجهزة أقوى.
5. سجّل الدخول بحسابك وشغّل.

## ملاحظات تقنية

- العميل مبني على **LWJGL 2.9.4** — نفس إصدار فانيلا 1.8.9، لذا طبقة توافق LWJGL2 في FCL تتعامل معه تماماً مثل فانيلا 1.8.9 / OptiFine.
- الـ JSON صيغة "نسخة مستقلة": يوفر `mainClass` (nick.Augustus) + أصول 1.8.9 + مدخل LWJGL واحد للتعرف على جيل LWJGL2، والجار الكامل يحمل كل شيء آخر.
- منصة ViaVersion/ViaLegacy مدمجة (اتصال بسيرفرات Alpha → 1.8.9+... حسب ما يدعمه العميل أصلاً).

## استكشاف الأخطاء

- **شاشة سوداء/كراش عند أول فريم:** جرّب تبديل العارض بين GL4ES و Holy-GL4ES و Krypton.
- **كراش متعلق بـ JNIC/native:** أرسل ملف اللوج (سجل FCL الأخير) لتحليله — عميل Augustus يحمل بعض الحمولات الأصلية المشفرة (dev/jnic) وقد تحتاج معالجة إضافية حسب العارض.
- **الأصوات:** تعمل عبر OpenAL الذي يوفره المشغل.

---

# English summary

OpenAugustus (Augustus b4.20.3 clean-source reconstruction on Minecraft 1.8.9 + OptiFine + Baritone) packaged as a standalone **Client Version** for **Fold Craft Launcher** on Android, with GL4ES / Holy-GL4ES / Krypton renderers.

- **Size: 347.95 MB → 171.43 MB (-50.7%)** via pure deduplication and Windows-only file removal. No game class, module (all 237), HUD element, or visual/audio asset was removed or modified.
- Automatic Android guards (music player JavaFX, SystemTray notifications, debug console, native extraction) — zero visual changes.
- Install: drop the jar+json into `versions/OpenAugustus-Android-b4.20.3/` in FCL's game dir, select the version, pick a GL4ES-class renderer. Java 8 (jre-legacy) is requested automatically; 1.8.9 assets are downloaded by the launcher.
- LWJGL 2.9.4 — identical to vanilla 1.8.9, so FCL's LWJGL2 compatibility layer applies as with vanilla.
