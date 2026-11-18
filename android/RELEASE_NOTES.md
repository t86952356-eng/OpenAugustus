# OpenAugustus b4.20.4 — Android Client Version (1.8.9)

نسخة **OpenAugustus** (Augustus b4.20.3 — مصدر نظيف 100% على Minecraft 1.8.9 + OptiFine + Baritone) المعدّلة لتعمل على **أندرويد** عبر **Fold Craft Launcher (FCL)** مع عارض **GL4ES / Holy-GL4ES أو Krypton (NG-GL4ES)** — بنظام **Client Version** مستقل.

- الملفات: `OpenAugustus-Android-b4.20.4.jar` (العميل الكامل) + `OpenAugustus-Android-b4.20.4.json` (ملف الإصدار) + `android-package-report.json` (تقرير التغليف والإصلاحات).
- المصدر: https://github.com/t86952356-eng/OpenAugustus

## ⚠️ حالة هذا الإصدار — اقرأها أولاً

**b4.20.4 يصلح كراش الإقلاع الفوري الموجود في b4.20.3 بالكامل** — سلسلة الإقلاع
(launcher.41 ← الجلسة 4v ← Controller ← المحمّل 444 ← AugustusClassLoader ←
الأوفيرلاي ← المفاتيح ← الموارد) تعمل الآن بالكامل على أندرويد بدون أي
`UnsatisfiedLinkError` — تم التحقق منها على CI بإعادة مسار الجهاز حرفياً.

**لكن العميل لن يصل إلى القائمة الرئيسية بعد.** بعد إصلاح كل ما سبق، يتوقف
الإقلاع عند جدار **معماري غير قابل للإصلاح كـ«مشكلة تشغيل»**:

| العنصر المحمي | وظيفته | لماذا لا يعمل على أندرويد |
|---|---|---|
| `net.47Uj.main` | **مُقلع اللعبة نفسه** (يستدعيه `StartMinecraftDirectory`) | JNIC native — منطقه موجود فقط كـ DLL ويندوز x64 |
| `net.40U` | نواة العميل (حاوية الخدمات — تستدعيها ~100 كلاس نظيف) | JNIC native — نفس السبب |
| `net.47R3` | ناقل الأحداث (Event Bus) | JNIC native |
| `net.47Ua` | معالج الاتصالات (Netty) | JNIC native |
| `net.47bj` | أداة مساعدة للنواة | JNIC native |

الحمولة الأصلية (`dev/jnic/lib/*.dat` — 1,146,368 بايت) **تدعم Windows x64
فقط** — لا توجد نسخة linux/aarch64 ولا يمكن توليدها؛ الكود لا يوجد إلا بهذه
الصيغة. تشغيل العميل كاملاً على أندرويد يتطلب **إعادة هندسة كاملة للمنطق
المحمي** (مشروع أسابيع من الهندسة العكسية، وليس إصلاحاً).

**بدل الكراش الغامض**، سيعرض العميل الآن رسالة تشخيص واضحة في سجل FCL تبدأ بـ
`OpenAugustus/Android:` وتشرح بالضبط أين الجدار ولماذا.

## ما الذي أُصلح فعلياً في b4.20.4 (موثق بالتجربة)

**الكراش القديم (b4.20.3):**
```
java.lang.UnsatisfiedLinkError: Platform not supported: linux/aarch64
	at dev.jnic.rNBrJa.JNICLoader.<clinit>
	at launcher.41.<clinit>
	at nick.Augustus.main(Augustus.java:26)
```

**السبب الجذري:** طبقتا حماية JNIC (تحويل كود Java إلى native):
1. `dev.jnic.rNBrJa.JNICLoader` داخل `loader/ElectricLauncher.jar` —
   `<clinit>` يفحص `os.name/os.arch` ولا يوجد فرع إلا لـ `win + x86_64/amd64`
   → يرمي `UnsatisfiedLinkError` فوراً على أي منصة أخرى.
2. `dev.jnic.aqRLGH.JNICLoader` — محمّل العميل المحمي (يُفك من الحمولات
   المشفرة في `data/classes.bin` وقت التشغيل) — نفس فحص المنصة.

**الإصلاحات (كلها تلقائية في سكربت التغليف، مع بوابات تحقق):**
1. **stubs آمنة للمحمّلَين** (`dev/jnic/rNBrJa` + `dev/jnic/aqRLGH`) — تُحقن
   في جذر الجار (ظهور أولوية-الأب لـ URLClassLoader الخاص بـ ElectricLauncher)
   **و** داخل الأوفيرلاي المدمج (ظهور لأولوية `cached` في AugustusClassLoader).
2. **تحييد خطافات JNIC** (`$jnicLoader` / `$jnicClinit` النيتفية) في 9 كلاسات
   عبر ASM — مع إبقاء `$jnicClinit` ذات الجسم الجافا (تهيئة مفاتيح ZKM)
   تعمل كما هي. الكلاسات: `launcher.41/44p/46e/46z` + `net.40U/47R3/47Ua/47Uj/47bj`.
3. **JavaFX markers** (18 نوعاً) يحتاجها تعريف `launcher.Controller` —
   JRE8 الخاص بالمشغلات لا يحتوي JavaFX و`Class.getDeclaredFields` يحل أنواع
   الحقول فوراً (`javafx.scene.media.*` متعمد عدم حقنه — كاشف الموسيقى
   `net.47TB` يعتمد على غيابه ليعطّل الموسيقى بأمان).
4. **تشخيص صريح** بدل `net.47Uj.main` النيتفي.
5. **بروب مرحلة 2 جديد في CI**: يشغّل `nick.Augustus.main` نفسه (مسار الجهاز
   حرفياً) على JVM 8 بدون شاشة ويتحقق أن الإقلاع يصل إلى الجدار الموثق —
   أي أن أي تراجع مستقبلي في سلسلة الإقلاع سيُمسك تلقائياً.

## حمايات أندرويد المدمجة (من b4.20.3 — كلها تلقائية، بلا أي تغيير بصري)

- **مشغل الموسيقى (JavaFX AudioClip):** يتحول لوضع صامت آمن بدل `NoClassDefFoundError`.
- **إشعارات سطح المكتب (SystemTray):** معطلة بأمان على JVM بلا واجهة.
- **Debug Console (Swing):** يتحقق من وضع headless قبل فتح أي نافذة.
- **استخراج الـ DLLs:** يتخطى المكتبات الغائبة بأمان.
- **ClickGUI و HUD والموديولات الـ 237: صفر تعديل.**

## الحجم: 347.95 MB ← 171.43 MB (تخفيف 50.7%)

كل التخفيف من **إزالة الازدواجية وحذف ملفات ويندوز فقط** — لم يُحذف أي كلاس
لعبة أو موديول أو عنصر HUD أو أصل بصري/صوتي: `data/resources.bin` المكررة
(80MB) + مداخل resources.jar المكررة (66MB) + cache.bin المغطاة بالأوفيرلاي
(43MB) + 16 DLL ويندوز (9MB) + ترجمة `-g:none`.

## التثبيت على FCL (Fold Craft Launcher)

1. حمّل `OpenAugustus-Android-b4.20.4.jar` و `OpenAugustus-Android-b4.20.4.json`.
2. في مجلد FCL: `files/.minecraft/versions/OpenAugustus-Android-b4.20.4/`
   (أو مسار اللعبة الظاهر في إعدادات FCL)
   - ضع الملفين داخل المجلد **بنفس الاسم**:
     - `versions/OpenAugustus-Android-b4.20.4/OpenAugustus-Android-b4.20.4.jar`
     - `versions/OpenAugustus-Android-b4.20.4/OpenAugustus-Android-b4.20.4.json`
3. شغّل FCL ← الإصدارات ← اختر **OpenAugustus-Android-b4.20.4**.
   - FCL سينزّل أصول Minecraft 1.8.9 الرسمية تلقائياً (assets 1.8) في أول تشغيل.
   - الـ JSON يطلب **Java 8 (jre-legacy)** تلقائياً.
4. العارض: **GL4ES** أو **Holy-GL4ES** — أو Krypton/NG-GL4ES إن توفر.
5. سترى في سجل FCL رسالة `OpenAugustus/Android: ...` بدل الكراش القديم —
   اقرأ «حالة هذا الإصدار» أعلاه.

## ملاحظات تقنية

- العميل مبني على **LWJGL 2.9.4** — نفس فانيلا 1.8.9، لذا طبقة توافق LWJGL2
  في FCL تتعامل معه مثل فانيلا 1.8.9 / OptiFine تماماً.
- الـ JSON صيغة «نسخة مستقلة»: `mainClass` = `nick.Augustus` + أصول 1.8.9 +
  مدخل LWJGL واحد (لتصنيف جيل LWJGL2)، والجار الكامل يحمل كل شيء آخر.
- كلاسات اللعبة (net/minecraft وغيرها) تُفك وقت التشغيل من الحمولات المشفرة
  عبر `launcher.444` (جافا خالص — يعمل على أندرويد).

## الخطوات التالية الممكنة (إن أردت المتابعة)

1. **إعادة هندسة النواة المحمية** (47Uj + 40U + 47R3 + 47Ua + 47bj): مشروع
   هندسة عكسية كبير بنتائج غير مضمونة — الحمولة native والمنطق غير مرئي.
2. **نسخة «لعبة فقط»**: يمكن نظرياً إقلاع ماينكرافت+OptiFine من الحمولات
   المشفرة بدون طبقة Augustus (يتطلب تفكيك مخطط تسمية الحمولات) — لكن هذا
   يسقط موديولات/HUD العميل (خيار غير مطابق لطلبك، لذا لم يُنفذ).
3. **SigmaNG 1.16.4** (المشغل السابق الذي نجح على جهازك) يعمل كاملاً إن
   احتجت عميلاً جاهزاً الآن.

---

# English summary

OpenAugustus (Augustus b4.20.3 clean-source reconstruction on Minecraft 1.8.9 +
OptiFine + Baritone) packaged as a standalone **Client Version** for **Fold Craft
Launcher** on Android (GL4ES / Holy-GL4ES / Krypton renderers).

**Status of this release (honest):** b4.20.4 fully fixes the b4.20.3 instant
crash (`UnsatisfiedLinkError: Platform not supported: linux/aarch64` in
`launcher.41.<clinit>` via the JNIC runtime): the entire launcher bootstrap
chain now runs on Android, verified on CI by replaying the exact device boot
path on a headless JVM 8. However, the client then stops at a **structural
wall**: the game bootstrap (`net.47Uj.main`) and the client core
(`net.40U/47R3/47Ua/47bj`) are JNIC-protected native code compiled for
**Windows x64 only** — no linux/aarch64 payload exists or can be produced.
Instead of a cryptic crash the client now prints an explicit diagnostic
explaining the wall. Full Android support would require reimplementing the
protected native core (a multi-week reverse-engineering effort), or
alternatively a game-only variant (without the Augustus module layer). Size:
347.95 MB → 171.43 MB (-50.7%, pure dedup, no module/HUD/asset removal).
