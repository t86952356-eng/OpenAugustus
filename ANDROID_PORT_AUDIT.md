# OpenAugustus Android Port — Audit Report (b4.20.3)

تقرير التدقيق الفني لتحويل OpenAugustus إلى Minecraft Client Version مستقل لأندرويد،
وفق منهجية التدقيق (جرد → تصنيف → تتبع نقاط الدخول → تعديل موثق → اختبارات).

## 1. جرد المشروع

| المكوّن | الحجم | التصنيف | المصير |
|---|---|---|---|
| `src/dependency/java/` (4,711 كلاس أساسي) | 37 MB | CORE | مبني كاملاً — لم يُحذف منه سوى صفر كلاسات؛ 4 كلاسات بنية تحتية حُميت (انظر §4) |
| `src/main/java/augustus/modules/` (237 موديول) | — | CORE (ممنوع التعديل) | **صفر تعديل** — بُنيت كما هي |
| `src/main/java/augustus/custom/` (11) | — | CORE | صفر تعديل |
| `src/runtime/java/nick/` (8 كلاسات إقلاع) | 56 KB | CORE (بنية تحتية للتشغيل) | 2 معدلة: Data.java, Libraries.java (انظر §4) |
| `src/main/resources/` (1,008 أصول قابلة للتحرير) | 69.6 MB | CORE (أصول بصرية/صوتية) | صفر حذف — تُشحن مرة واحدة عند جذر الجار |
| `lib/launcher-base.jar` (مُعاد تجميعه من build-inputs/parts) | 272 MB | CORE | أساس البناء |
| `data/classes.bin` (35,898 مدخل: مكتبات + 7,079 حمولات مشفرة SHA) | 68.2 MB | CORE | كامل — لم يُحذف منه شيء |
| `data/resources.bin` (5,738 مدخل) | 80 MB | **مكرر 100%** | حُذف — الخريطة تُبنى من resources.jar |
| `data/cache.bin` (3,949 كلاس عميل) | 44 MB | CORE (3,341 منها مكررة بالـ overlay) | استُبقي 608 فقط (غير المغطاة) — ببوابة تحقق |
| `data/keys.bin` | 290 KB | CORE | كامل |
| `loader/resources.jar` (5,738 مدخل) | 84 MB | CORE (1,007 منها مكررة عند جذر الجار) | استُبقي 4,731 مدخل غير قابل للتحرير |
| `loader/ElectricLauncher.jar` (6,025 كلاس) | 13.6 MB | CORE (محمي ZKM) | كامل — لم يُلمس |
| `natives/*.dll` (16 DLL ويندوز x86/x64) | 9 MB | DESKTOP_ONLY | حُذفت — FCL يوفر مكتبات المنصة |
| `recovery/compiled-source-overlay.jar` (5,186 كلاس نظيف) | 9.2 MB | CORE | كامل |
| `lib/runtime/javafx8/` | 101 MB | BUILD_ONLY (ترويسات ترجمة) | خارج الجار أصلاً — لم يُلمس |
| `tibo34.png`, docs/, tools/ | — | BUILD_ONLY | خارج الجار |

## 2. سلسلة التشغيل (Runtime chain)

```
java -jar OpenAugustus-Android-b4.20.3.jar
 └─ nick.Augustus.main()
     ├─ Libraries.loader()      → يستخرج loader/ElectricLauncher.jar لمؤقت ويحمّله URLClassLoader
     ├─ Unsafe + session tokens → تهيئة launcher.41 / launcher.4v / launcher.444 / Controller
     ├─ Data.classes()          → خريطة من data/classes.bin (35,898)
     ├─ Data.resources()        → [معدّل] خريطة من loader/resources.jar (zip) + دمج 1,008 أصل قابل للتحرير
     ├─ Data.cache()            → [معدّل] خريطة من data/cache.bin المُقلَّص (608) — أو فارغة إن غاب
     ├─ AugustusClassLoader     → cached = cache + patches(472g/47eJ/47Ua/47cq) + EmbeddedOverlay(putAll — الأعلى أولوية)
     ├─ Data.keys()             → حقول مفاتيح ZKM على الـ delegate loader
     ├─ كتابة resources.jar لمسار AppData (كما في الأصل)
     ├─ Libraries.create()      → [معدّل] تخطي الـ natives الغائبة بأمان
     └─ StartMinecraftDirectory.main() → اللعبة (LWJGL 2.9.4 + natives المشغل)
```

أولوية تحميل الكلاسات: `cached` (cache + overlay) ← `classes.bin` ← delegate loader.

## 3. تحليل الحجم (لماذا 348 MB؟)

الجار الأصلي يشحن نفس البيانات أكثر من مرة:
1. **الأصول مرتين**: `data/resources.bin` و `loader/resources.jar` متطابقان بايت-ببايت (تحقق: 5,738/5,738 مدخل، 0 اختلاف في عينة 3,000).
2. **الأصول القابلة للتحرير مرتين إضافيتين**: 1,007 من أصل 1,008 موجودة داخل resources.jar AND عند جذر الجار (تُدمج فوق الخريطة عبر EditableResources.mergeInto في كل إقلاع — نسخة الجذر هي الفائزة).
3. **كلاسات العميل مرتين**: 3,341 كلاس في cache.bin مغطاة بالكامل بالـ overlay المدمج الذي يعلوها أولوية (cached.putAll).
4. **16 DLL ويندوز** لا معنى لها على أندرويد.

## 4. التعديلات المصدرية (6 ملفات — كلها بنية تحتية، صفر موديولات/HUD)

| الملف | التعديل | الدليل/السبب |
|---|---|---|
| `src/runtime/java/nick/Data.java` | `resources()` يبني الخريطة من `loader/resources.jar` (zip) بدل `data/resources.bin`؛ `cache()` يقبل غياب الحمولة | إزالة الازدواجية 80 MB؛ المحتوى متطابق بايت-ببايت (§3.1) |
| `src/runtime/java/nick/Libraries.java` | تخطي الـ natives الغائبة؛ لا تعديل java.library.path إن لم يُستخرج شيء | أندرويد بلا DLLs؛ FCL يزوّد lwjgl/openal |
| `client/util/AudioClipPlayer.java` | فحص `Class.forName("javafx.scene.media.AudioClip")` مرة واحدة؛ كل الدوال no-op عند الغياب | Temurin 8 (مشغلات أندرويد) بلا JavaFX → `NoClassDefFoundError` عند أي تشغيل موسيقى (المسار يُستدعى من Minecraft.java) |
| `client/util/SystemTrayNotifier.java` | فحص headless/isSupported قبل الإنشاء؛ `applyString` محمي بالكامل | `TrayIcon.displayMessage` يرمي `HeadlessException` غير ممسوك على JVM بلا واجهة — كان سيكرش عند كل تفعيل موديول مع OldNotification |
| `client/util/DebugConsoleJFrame.java` | فحص `GraphicsEnvironment.isHeadless()` مبكراً | نافذة Swing debug — نفس مسار HeadlessException الموجود لكن قبل أي استدعاء AWT |
| `net/minecraft/item/IronBoots.java` (كلاس تسلسل إعدادات، اسم مُضلل من فك التشويش) | تحويل ternary مُحوَّل بـ cast إلى if/else | javac 17.0.21 كان يصدر إطار StackMapTable من نوع Object لنقطة الدمج → `VerifyError` تحت `-Xverify:all` (فشل البناء على لينكس؛ الدلالات متطابقة) |

**ما لم يُلمس إطلاقاً:** الـ 237 موديول، ClickGUI، HUD، الأصول البصرية/الصوتية، ElectricLauncher.jar (محمي ZKM)، classes.bin، keys.bin، أصول الجذر.

## 5. ملف JSON (Client Version لـ FCL)

- `id: OpenAugustus-Android-b4.20.3`، `mainClass: nick.Augustus` (Main-Class الجار نفسه)
- `minecraftArguments` / `assetIndex (1.8)` / `assets` منسوخة حرفياً من manifest فانيلا 1.8.9 الرسمي
- `javaVersion: jre-legacy (8)` — من فانيلا 1.8.9 (FCL يختار Java 8 تلقائياً)
- مدخل مكتبة واحد `org.lwjgl.lwjgl:lwjgl:2.9.4-nightly-20150209` — لتصنيف FCL للنسخة كجيل LWJGL2 فيختار natives التوافق المناسبة (نفس آلية فانيلا 1.8.9؛ كلاسات LWJGL 2.9.4 Java مضمّنة داخل الجار في classes.bin)
- `downloads.client` = الجار الكامل من رابط الـ release

## 6. المخاطر المتبقية (موثقة بصدق)

1. **JNIC (net/47Ua + dev/jnic/lib/*.dat):** العميل يحمل حمولات أصلية مشفرة (3.72 MB + أخرى). لو كان أحد مساراتها إلزامياً وقت الإقلاع على أندرويد فقد يظهر `UnsatisfiedLinkError` — لم يظهر في أي فحص محلي (البيانات تُحمّل كسلاسل، والفك يتم عند الطلب) — إن ظهر على الجهاز فهو أول إصلاح تالٍ.
2. **قارئ ملف resources.jar الخارجي (AppData):** الجار يكتب الملف في كل إقلاع (سلوك أصلي) لكن لا مرجع نصي له داخل ElectricLauncher (فحص 6,025 كلاس). أُبقي الكتابة كما هي للتوافق.
3. **جودة العارض:** شيدرات العميل (blur/glow/kawase — 130 ملف GLSL) تعتمد على قدرة العارض؛ على GLES2 قد تتدهور بصرياً (لا كراش — مسارات GLSL فردية).

## 7. الاختبارات المنفذة فعلياً (أدلة)

- **بناء كامل من المصدر على لينكس**: `python3 build.py` — 4,959 مصدر → 237 موديول + 4,772 كلاس أساسي، `BUILD PASSED`، بوابات upstream كلها (تطابق البصمات، CRC، IRC removal، `-Xverify:all` على HotSpot Java 8) = PASS.
- **verify.py الرسمي**: `VERIFY PASSED` (بصمات المصادر، تضمين الجار، 155 كلاس JInput، حذف IRC في الخرائط الثلاث).
- **التغليف**: كل بوابات التحقق مرّت (تغطية cache 100%، 1,007 أصل مقصوص بمطابقة الفهرس، بقاء كلاسات الترقيع الأربعة).
- **ProbeAugustus (Java 8, جار العميل وحده)**: 26/26 فحص = `PROBE-PASSED` — يعيد إنتاج كل مسارات تحميل البيانات قبل OpenGL (classes 35,898 / resources 5,739 / cache 608 / keys / overlay 5,186 / natives غائبة ومتخطاة).
- **لم يُختبر على جهاز أندرويد حقيقي بعد** — أول تشغيل على FCL هو الاختبار الحقيقي التالي.

## 8. أفكار تخفيف إضافية (نسخة قادمة إن لزم)

- استبعاد كلاسات المكتبات المطابقة بايت-ببايت لمكتبات فانيلا 1.8.9 من classes.bin (مع inheritsFrom + fallback للـ classpath) — قد يوفر ~20-30 MB إضافية.
- تجريد LineNumberTable من كلاسات المكتبات (35,898) — ~8-10 MB مقابل وقت بناء أطول.
- إعادة ضغط أصوات OGG بمعدل بت أقل — **مرفوض حالياً** (يغير الأصول الصوتية).

## 9. إصلاح كراش الإقلاع على الجهاز (b4.20.4) — التشريح الكامل

### الكراش (تقرير FCL من جهاز حقيقي — Infinix X6833B / MT6789 / Holy-GL4ES)

```
java.lang.reflect.InvocationTargetException
	at mio.Wrapper.main(Wrapper.java:21)
Caused by: java.lang.UnsatisfiedLinkError: Platform not supported: linux/aarch64
	at dev.jnic.rNBrJa.JNICLoader.<clinit>(Unknown Source)
	at launcher.41.<clinit>(41.java)
	at sun.misc.Unsafe.ensureClassInitialized(Native Method)
	at nick.Augustus.main(Augustus.java:26)
```

### التتبع الجنائي (أدلة bytecode — لا تخمين)

1. **حمولة JNIC ويندوز فقط**: تفكيك `<clinit>` الخاص بـ
   `dev.jnic.rNBrJa.JNICLoader` (داخل ElectricLauncher.jar) يُظهر فرعاً
   واحداً فقط: `os.name.contains("win") && (x86_64|amd64)` → استخراج
   `[0, 1146368)` من `dev/jnic/lib/0ddbcb95-….dat` (مفكوك LZMA عبر
   JNICLoader نفسه — يرث InputStream) ثم `System.load`. أي منصة أخرى →
   `start == length == 0` → رمي «Platform not supported».
2. **خطاف الإقلاع**: `launcher/41.class` (Thread) كتلة ساكنة:
   `{ JNICLoader.init(); $jnicLoader(); $jnicClinit(); }` — و`$jnicLoader`
   **native** — أي أن تحييد JNICLoader وحده لا يكفي.
3. **طبقة حماية ثانية**: كلاسات نواة العميل (الأوفيرلاي الأصلي المحفوظ من
   base-runtime-overlay — `PRESERVE_BINARY_CLASSES` في build.py) تستورد
   `dev.jnic.aqRLGH.JNICLoader` (حزمة مختلفة!) — محمّلها يُفك من الحمولات
   المشفرة في classes.bin وقت التشغيل، ونفس فحص المنصة بداخلها.
4. **الجدار الثالث**: `launcher.Controller` (يُنشأ في المصافحة عبر
   `nick.Augustus` سطر 35) يعلن حقول JavaFX (`Text/Button/ListView/...`)
   و`Class.getDeclaredFields` (آلية ZKM المغلقة) يحل أنواع الحقول **فوراً**
   → `NoClassDefFoundError: javafx/scene/text/Text` (لا JavaFX في JRE8
   الخاص بالمشغلات).
5. **الجدار الرابع — القاتل**: بعد إصلاح كل ما سبق (تحقّق تجريبي كامل على
   لينكس/JDK8 بإعادة `nick.Augustus.main` حرفياً):
   - `StartMinecraftDirectory.main` (الأوفيرلاي) يستدعي **`net.47Uj.main`**
     وهي **native بالكامل** — مُقلع اللعبة الفعلي (`49`/Main المقروء مجرد
     غلاف يعيد الاستدعاء إلى 47Uj نفسها).
   - نواة العميل `net.40U` (حاوية الخدمات — `40U.44().45()…` في ~100 كلاس
     نظيف) و`net.47R3` (ناقل الأحداث) و`net.47Ua` (معالج Netty) و`net.47bj`
     — كل منطقها native في الحمولة، **لا يوجد لها سورس** (SKIP_BINARY_CLASSES
     في build.py) ولا نسخة aarch64.

### الاستنتاج المعماري (موثق بأدلة)

كامل سلسلة الإقلاع **قابلة للإصلاح وتُصلحت**؛ أما مُقلع اللعبة ونواة
العميل فهما منطق native بملفات Windows x64 فقط — تشغيلهما على أندرويد
يتطلب إعادة هندسة كاملة (مشروع هندسة عكسية)، ولا يوجد أي مسار «إصلاح
تشغيلي» لهما.

### إصلاحات b4.20.4 (كلها في `android/package_android.py` — ببوابات تحقق)

| الإصلاح | الآلية |
|---|---|
| محمّلا JNIC آمنان | `dev/jnic/{rNBrJa,aqRLGH}/JNICLoader` stubs ذاتية الاحتواء (تخصيص `z` + `init()` فارغ + `<clinit>` لا يرمي أبداً) — تُحقن في **جذر الجار** (أولوية-الأب لـ URLClassLoader الخاص بـ ElectricLauncher) **وفي الأوفيرلاي المدمج** (أولوية `cached` في AugustusClassLoader الذي لا يفوّض للأب) |
| خطافات JNIC | `$jnicLoader` (و`$jnicClinit` النيتفية فقط) تُحوّل لجسم فارغ عبر ASM (`android/PatchJnic.java`) في: `launcher/41/44p/46e/46z` + `net/40U/47R3/47Ua/47Uj/47bj`. `$jnicClinit` ذات الجسم الجافا (تهيئة ZKM/DES في 41 وController و47Ua) تعمل كما هي |
| JavaFX | 18 marker stub فارغ لأنواع Controller (واجهة + كلاسات) — **لا** يُحقن `javafx.scene.media.*` (كاشف الموسيقى `net/47TB` يتحقق من الغياب ويعطّل بأمان) |
| مُقلع اللعبة | `net.47Uj.main` تُستبدل بتشخيص صريح (`PatchJnic.DIAG_MESSAGE`) بدل `UnsatisfiedLinkError` غامض |
| بوابات التغليف | فحص bytecode بعد الترقيع: `$jnicLoader/$jnicClinit` لم يعدا native، الـ stubs موجودة في الجذر والأوفيرلاي |

### الاختبارات المنفذة فعلياً (أدلة)

- **تشغيل كامل محلياً (لينكس x86_64 + Temurin JDK 8u422)**: جار b4.20.3
  المرقّع بالإصلاحات يقصّ `nick.Augustus.main` كاملة: تهيئة `launcher.41` ✓
  (كانت الكراش)، جلسة `4v` + التوكنات ✓، إنشاء `Controller` ✓ (JavaFX
  stubs)، محمّل `444` ✓، `AugustusClassLoader` + أوفيرلاي 5,206 ✓،
  المفاتيح ✓، كتابة resources.jar ✓، `Libraries.create()` ✓، وصولاً إلى
  `net.47Uj.main` — حيث يتوقف عند الجدار الموثق بدل الانهيار الغامض.
- **بروب CI الجديد (المرحلة 2)**: `android/ProbeAugustus.java` يشغّل
  `nick.Augustus.main` نفسه على JVM 8 بدون شاشة ويتحقق أن السبب الجذري
  النهائي هو التشخيص الموثق (وليس `UnsatisfiedLinkError`) — أي أن أي
  تراجع في سلسلة الإقلاع يُمسك تلقائياً في كل بناء.
- **بوابات التغليف**: 33 فحصاً بنيوياً (المرحلة 1) + فحوص الترقيع كلها PASS.

### ما لم يُنفذ عمداً (وثوقية)

- إعادة هندسة `47Uj/40U/47R3/47Ua/47bj` — خارج نطاق «إصلاح تشغيلي»؛ تتطلب
  مشروع هندسة عكسية بنتائج غير مضمونة (المنطق غير موجود إلا كـ native).
- نسخة «لعبة فقط» (إقلاع vanilla من الحمولات بدون طبقة Augustus) — ممكنة
  نظرياً لكنها تسقط موديولات/HUD العميل (مخالفة لقيد عدم المساس بالموديولات).
