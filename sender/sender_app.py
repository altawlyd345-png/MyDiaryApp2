"""BLE Remote - SENDER v3.
Edit / save / preview are local. The Receiver changes only via an explicit, confirmed send."""
import copy, glob, hashlib, http.client, json, os, shutil, threading, time
from urllib.parse import quote
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Line, PushMatrix, PopMatrix, Rotate
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.colorpicker import ColorPicker
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import AsyncImage, Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as H
from protocol import Reassembler, encode, fragment, shape, to_bytes, dyn_text
from store import Store
import transfer
import studio as S
import secure_flow as SF
from layers_view import LayersView
import mediaplan
import workspace_model as WM
import zones as ZN

HERE = os.path.dirname(os.path.abspath(__file__))
def _fp(n): return os.path.join(HERE, "fonts", n)
# DejaVu first: it has Arabic joined forms AND Latin letters / brackets / dashes (Noto Naskh has Arabic only -> boxes).
APP_FONT = next((p for p in (_fp("DejaVuSans.ttf"), _fp("Amiri-Regular.ttf"), _fp("NotoNaskhArabic-Regular.ttf")) if os.path.exists(p)), _fp("DejaVuSans.ttf"))
BLUE, DARK, GREY, RED, GREEN = "#1565C0", "#0B0F1A", "#37474F", "#B71C1C", "#00897B"
BASE_BLUE = BLUE
LOCATION = "android.permission.ACCESS_FINE_LOCATION"
PERMS = ["android.permission.BLUETOOTH_CONNECT", "android.permission.BLUETOOTH_SCAN", LOCATION]   # Android 12+ (API 31+)
PERMS_LEGACY = [LOCATION]       # Android 10/11 (e.g. Galaxy A11): BLUETOOTH_SCAN/CONNECT do not exist, scanning needs Location
COLORS = {"أسود": "#000000", "أبيض": "#FFFFFF", "أزرق": "#1565C0", "أحمر": "#D32F2F",
          "أخضر": "#2E7D32", "أصفر": "#FDD835", "برتقالي": "#EF6C00"}
STATES = {"idle": "غير متصل", "scanning": "جاري البحث...", "connecting": "جاري الاتصال...",
          "ready": "متصل ✔", "disconnected": "انقطع الاتصال", "bt_off": "فعّل البلوتوث",
          "no_service": "الجهاز لا يحتوي الخدمة", "scan_failed": "فشل البحث",
          "perm_denied": "امنح صلاحية الموقع / الأجهزة القريبة للتطبيق", "location_off": "فعّل خدمة الموقع (GPS) ثم أعد الاتصال",
          "error": "خطأ بلوتوث - أعد الاتصال"}
F = {"font_name": APP_FONT} if os.path.exists(APP_FONT) else {}
ALIGN = {"يمين": "right", "وسط": "center", "يسار": "left"}
MODES = {"ثابت": "static", "شريط أخبار أفقي": "ticker_h", "شريط عمودي": "ticker_v", "وميض": "blink",
         "كتابة تدريجية": "typewriter", "ظهور تدريجي": "fade", "ظهور واختفاء": "fade_loop"}
TDIRS = {"حركة من اليمين لليسار": "r2l", "حركة من اليسار لليمين": "l2r"}
KINDS = {"image": "صورة", "video": "فيديو", "audio": "صوت"}
TYPES = {"layer": "التحكم بطبقة", "apply_scene": "عرض مشهد", "apply_design": "عرض تصميم", "apply_playlist": "قائمة تشغيل", "clear": "مسح الشاشة",
         "hide": "إخفاء", "restore": "استعادة العرض", "ping": "اختبار اتصال", "reload": "إعادة تحميل",
         "next": "التالي", "prev": "السابق", "emergency": "رسالة طوارئ", "emergency_off": "إيقاف الطوارئ",
         "hello": "اتصال", "pair_begin": "اقتران", "pair_confirm": "تأكيد الاقتران", "status": "حالة جهاز العرض", "unpair": "إلغاء الاقتران", "brightness": "السطوع", "media": "تحكم بالتشغيل", "transition": "انتقال المشاهد", "store_project": "تجهيز مشروع", "play_project": "تشغيل مشروع", "command": "أمر نصي للمستقبل"}
TRANS = {"بدون": "none", "تلاشي": "fade", "انزلاق لليسار": "slide_left",
         "انزلاق لليمين": "slide_right", "انزلاق للأعلى": "slide_up",
         "انزلاق للأسفل": "slide_down", "تكبير": "zoom"}
ZONE_SETS = [
    ("عمودان متساويان", [(0, 0, .5, 1), (.5, 0, .5, 1)]),
    ("صفان متساويان", [(0, 0, 1, .5), (0, .5, 1, .5)]),
    ("أربع مناطق", [(0, 0, .5, .5), (.5, 0, .5, .5), (0, .5, .5, .5), (.5, .5, .5, .5)]),
    ("ست مناطق", [(0, 0, 1/3, .5), (1/3, 0, 1/3, .5), (2/3, 0, 1/3, .5),
                   (0, .5, 1/3, .5), (1/3, .5, 1/3, .5), (2/3, .5, 1/3, .5)]),
    ("ثلاثة أعمدة", [(0, 0, 1/3, 1), (1/3, 0, 1/3, 1), (2/3, 0, 1/3, 1)]),
    ("رئيسية مع شريط جانبي", [(0, 0, .68, 1), (.68, 2/3, .32, 1/3), (.68, 1/3, .32, 1/3), (.68, 0, .32, 1/3)]),
    ("رأس ووسط وتذييل", [(0, .86, 1, .14), (0, .14, 1, .72), (0, 0, 1, .14)]),
]
PICK_REQ = 7711

def human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB": return ("%d %s" % (n, u)) if u == "B" else ("%.1f %s" % (n, u))
        n /= 1024

def T(s): return shape(s)
def pick(d, text, default):
    return next((v for k, v in d.items() if T(k) == text), default)

def L(text, h=None, **kw):
    kw = {**F, "color": (1, 1, 1, 1), "halign": "center", "valign": "middle", **kw}
    l = Label(text=T(text), **kw)
    l.bind(size=lambda i, v: setattr(i, "text_size", v))
    if h: l.size_hint_y = None; l.height = dp(h)
    return l

def B(text, cb, color=None, h=48, wx=None):
    color = color or BLUE
    b = Button(text=T(text), background_normal="", background_color=H(color), size_hint_y=None, height=dp(h), **F)
    if wx: b.size_hint_x = wx
    b.bind(on_release=lambda *_: cb()); return b

def _vis(text):
    """Visual (joined, right-to-left) form of typed text; the field itself keeps the raw text."""
    try:
        if not isinstance(text, str) or not any("\u0600" <= c <= "\u06FF" for c in text): return text
        if any("\uFB50" <= c <= "\uFEFF" for c in text): return text   # already shaped
        return "\n".join(shape(line) for line in text.split("\n"))
    except Exception:
        return text

class ArTextInput(TextInput):
    """TextInput that joins Arabic letters when drawing (Kivy does no shaping by itself)."""
    if hasattr(TextInput, "_create_line_label"):
        def _create_line_label(self, text, hint=False):
            return super()._create_line_label(text if (hint or self.password) else _vis(text), hint)
    if hasattr(TextInput, "_get_text_width"):
        def _get_text_width(self, text, *a, **k):
            return super()._get_text_width(text if self.password else _vis(text), *a, **k)

def _patch_core_label():
    """Safety net: every Kivy text render goes through core Label.text, so join Arabic there too
    (covers TextInput on any Kivy version). Already-shaped text is left untouched by _vis()."""
    try:
        from kivy.core.text import LabelBase
        if getattr(LabelBase, "_ar_patched", False): return
        prop = LabelBase.__dict__.get("text")
        if not isinstance(prop, property) or prop.fget is None: return
        fget, fset, doc = prop.fget, prop.fset, prop.__doc__
        def _get(self):
            t = fget(self)
            return _vis(t) if isinstance(t, str) else t
        LabelBase.text = property(_get, fset, None, doc)
        if isinstance(LabelBase.__dict__.get("label"), property): LabelBase.label = LabelBase.text
        LabelBase._ar_patched = True
    except Exception:
        pass
_patch_core_label()

def TI(text="", hint="", ml=False, h=44, **kw):
    if hasattr(TextInput, "halign"): kw.setdefault("halign", "right")
    return ArTextInput(text=text, hint_text=T(hint) if hint else "", multiline=ml, size_hint_y=None,
                     height=dp(h), **{**F, **kw})

def popup(title, content, size=(0.94, 0.8)):
    p = Popup(title=T(title), content=content, size_hint=size, title_font=APP_FONT if F else "Roboto")
    p.open(); return p

def confirm(msg, yes):
    box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
    box.add_widget(L(msg))
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    p = popup("تأكيد", box, (0.9, 0.4))
    row.add_widget(B("إلغاء", p.dismiss, GREY))
    row.add_widget(B("تأكيد", lambda: (p.dismiss(), yes()), GREEN))
    box.add_widget(row)

class SpOpt(SpinnerOption):
    def __init__(self, **kw):
        kw.setdefault("font_name", APP_FONT); super().__init__(**kw)

def SP(text, values, **kw):
    return Spinner(text=text, values=values, option_cls=SpOpt, size_hint_y=None, height=dp(44), **{**F, **kw})

SWATCH = ["#000000", "#FFFFFF", "#1565C0", "#D32F2F", "#2E7D32", "#FDD835", "#EF6C00"]

def pick_color(title, current, cb):
    box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
    p = popup(title, box, (0.96, 0.92))
    cp = ColorPicker(color=H(current))
    sw = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
    for c in SWATCH:
        sw.add_widget(Button(background_normal="", background_color=H(c),
                             on_release=lambda x, c=c: setattr(cp, "color", H(c))))
    hx = TI(hint="أو اكتب رمز اللون مثل #FF0000", h=40)
    def ok():
        t = hx.text.strip(); val = None
        if len(t) == 7 and t[0] == "#":
            try: int(t[1:], 16); val = t.upper()
            except ValueError: val = None
        if not val: val = "#%02X%02X%02X" % tuple(int(round(x * 255)) for x in cp.color[:3])
        p.dismiss(); cb(val)
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    row.add_widget(B("إلغاء", p.dismiss, GREY)); row.add_widget(B("اعتماد اللون", ok, GREEN))
    for w in (cp, sw, hx, row): box.add_widget(w)

V8_IN = {"بدون": "none", "تلاشي": "fade", "انزلاق لليمين": "slide_right", "انزلاق لليسار": "slide_left",
         "انزلاق من الأسفل": "slide_up", "انزلاق من الأعلى": "slide_down",
         "تكبير": "zoom_in", "تصغير": "zoom_out", "كتابة حرف بحرف": "typewriter", "ظهور كلمة بكلمة": "word", "ارتداد": "bounce"}
V8_OUT = {"بدون": "none", "تلاشي": "fade", "انزلاق لليمين": "slide_right", "انزلاق لليسار": "slide_left",
          "انزلاق للأعلى": "slide_up", "انزلاق للأسفل": "slide_down", "تصغير": "zoom_out"}
IMG_IN = {k: v for k, v in V8_IN.items() if v not in ("typewriter", "word")}
V8_MODE = {"مستمر": "continuous", "متتابع": "sequential", "ثابت": "static"}
V8_DIR = {"من اليمين لليسار": "rtl", "من اليسار لليمين": "ltr"}
V8_ALIGN = {"يمين": "right", "وسط": "center", "يسار": "left"}
V8_SEP = {"✦": "  ✦  ", "|": "  |  ", "●": "  ●  ", "◆": "  ◆  ", "★": "  ★  ", "—": "  —  ", "مسافة": "      "}
BUNDLED = {n: p for n, p in (("Amiri", "fonts/Amiri-Regular.ttf"), ("Noto Naskh", "fonts/NotoNaskhArabic-Regular.ttf")) if os.path.exists(p)}
V8_FONT = dict([("الافتراضي", "")] + [(n, n) for n in BUNDLED])

def scroll_grid(parent):
    sv = ScrollView(); g = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
    g.bind(minimum_height=g.setter("height")); sv.add_widget(g); parent.add_widget(sv); return g

def summary(sc):
    msgs = [m for m in (sc.get("text") or {}).get("msgs", []) if str(m).strip()]
    s = (str(msgs[0])[:24] if msgs else "بدون نص")
    extra = [KINDS[sc[k]["kind"]] for k in ("visual", "audio") if sc.get(k) and sc[k].get("kind") in KINDS]
    return s + ("  +" + " + ".join(extra) if extra else "")

class Page(Screen):
    def __init__(self, app, key, title):
        super().__init__(name=key)
        self.app = app
        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        hdr = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        hdr.add_widget(B("رجوع", lambda: app.go("home"), GREY, 44, 0.3))
        hdr.add_widget(L(title, font_size="20sp"))
        root.add_widget(hdr)
        self.body = BoxLayout(orientation="vertical", spacing=dp(6))
        root.add_widget(self.body)
        self.add_widget(root)
    def on_pre_enter(self, *a): self.refresh()
    def refresh(self): pass

# ---------- generic list pages ----------
class ListPage(Page):
    def __init__(self, app, key, title, col, fields, send=None, extra=None):
        super().__init__(app, key, title)
        self.col, self.fields, self.send, self.extra = col, fields, send, extra
        self.q = TI(hint="بحث بالاسم أو المحتوى")
        self.q.bind(text=lambda *_: self.refresh())
        self.body.add_widget(self.q)
        self.lst = scroll_grid(self.body)
        self.body.add_widget(B("+ جديد", lambda: self.edit({})))

    def refresh(self):
        self.lst.clear_widgets()
        for it in self.app.store.items(self.col, self.q.text):
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
            row.add_widget(L(("★ " if it.get("fav") else "") + it.get("name", "؟"), halign="right"))
            row.add_widget(B("★", lambda i=it: self.fav(i), GREY, 44, 0.12))
            row.add_widget(B("تعديل", lambda i=it: self.edit(i), GREY, 44, 0.25))
            row.add_widget(B("نسخ", lambda i=it: self.dup(i), GREY, 44, 0.2))
            row.add_widget(B("حذف", lambda i=it: self.rm(i), RED, 44, 0.2))
            if self.extra: row.add_widget(B(self.extra[0], lambda i=it: self.extra[1](i), BLUE, 44, 0.25))
            if self.send: row.add_widget(B("إرسال", lambda i=it: self.send(i), GREEN, 44, 0.25))
            self.lst.add_widget(row)

    def fav(self, it): it["fav"] = not it.get("fav"); self.app.store.put(self.col, it); self.refresh()
    def dup(self, it):
        c = copy.deepcopy(it); c.pop("id", None); c["name"] = it.get("name", "") + " (نسخة)"
        self.app.store.put(self.col, c); self.refresh()
    def rm(self, it): confirm("حذف نهائي؟", lambda: (self.app.store.delete(self.col, it["id"]), self.refresh()))

    def edit(self, it):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        ins = {}
        for key, label, ml in self.fields:
            box.add_widget(L(label, 22))
            ins[key] = TI(it.get(key, ""), ml=ml, h=150 if ml else 44)
            box.add_widget(ins[key])
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        p = popup("تحرير", box)
        def save():
            n = dict(it); n.update({k: v.text for k, v in ins.items()})
            if not n.get("name", "").strip(): n["name"] = "بدون اسم"
            self.app.store.put(self.col, n); p.dismiss(); self.refresh()
        row.add_widget(B("إلغاء", p.dismiss, GREY)); row.add_widget(B("حفظ (لا يرسل)", save, BLUE))
        box.add_widget(row)

# ---------- draggable text placement preview ----------
class TextPositionPreview(FloatLayout):
    """A normalized preview canvas; drag the text block to choose its screen position."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.position = {"x": 0.10, "y": 0.25, "w": 0.80, "h": 0.50}
        self.label = Label(text="", size_hint=(self.position["w"], self.position["h"]),
                           pos_hint={"x": self.position["x"], "y": self.position["y"]},
                           halign="center", valign="middle", **F)
        self.label.bind(size=lambda i, v: setattr(i, "text_size", v))
        with self.canvas.before:
            self.bg_color = Color(*H("#1565C0")); self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)
        self.add_widget(self.label)

    def _update_bg(self, *args):
        self.bg_rect.pos, self.bg_rect.size = self.pos, self.size

    def set_position(self, x, y):
        self.position["x"] = max(0.0, min(1.0 - self.position["w"], float(x)))
        self.position["y"] = max(0.0, min(1.0 - self.position["h"], float(y)))
        self.label.pos_hint = {"x": self.position["x"], "y": self.position["y"]}

    def on_touch_down(self, touch):
        if self.label.collide_point(*touch.pos) and self.collide_point(*touch.pos):
            touch.grab(self)
            self._move_to(touch)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self._move_to(touch)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    def _move_to(self, touch):
        if self.width <= 0 or self.height <= 0: return
        x = (touch.x - self.x) / self.width - self.position["w"] / 2
        y = (touch.y - self.y) / self.height - self.position["h"] / 2
        self.set_position(x, y)

# ---------- Text Studio (text + display mode + image/video/audio) ----------
class TextStudio(Page):
    def __init__(self, app):
        super().__init__(app, "text", "استوديو النصوص")
        self.fgc, self.bgc_ = "#FFFFFF", "#1565C0"
        self.media = {"visual": None, "audio": None}
        sv = ScrollView(); g = GridLayout(cols=1, size_hint_y=None, spacing=dp(6))
        g.bind(minimum_height=g.setter("height")); sv.add_widget(g); self.body.add_widget(sv)
        def row(h=44):
            r = BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(4)); g.add_widget(r); return r
        self.inp = TI(hint="اكتب النص هنا (عربي وإنجليزي)", ml=True, h=110); g.add_widget(self.inp)
        self.inp.bind(text=lambda *_: self.preview())
        self.multi = ToggleButton(text=T("كل سطر رسالة مستقلة (تتبدل تلقائياً)"), size_hint_y=None, height=dp(40), **F)
        g.add_widget(self.multi)
        r = row()
        self.size_in = TI("48", input_filter="int", h=44, size_hint_x=.2); self.size_in.bind(text=lambda *_: self.preview())
        self.fgb = B("لون النص", lambda: pick_color("لون النص", self.fgc, self.set_fg), GREY, 44)
        self.bgb = B("لون الخلفية", lambda: pick_color("لون الخلفية", self.bgc_, self.set_bg), BLUE, 44)
        self.align = SP(T("وسط"), [T(k) for k in ALIGN], size_hint_x=.25); self.align.bind(text=lambda *_: self.preview())
        for w in (self.size_in, self.fgb, self.bgb, self.align): r.add_widget(w)
        r = row()
        self.mode = SP(T("ثابت"), [T(k) for k in MODES])
        self.tdir = SP(T("حركة من اليمين لليسار"), [T(k) for k in TDIRS])
        r.add_widget(self.mode); r.add_widget(self.tdir)
        r = row()
        self.speed = Slider(min=1, max=10, value=5, step=1)
        self.hold = TI("5", input_filter="int", h=44, size_hint_x=.2)
        r.add_widget(L("المدة بالثواني", size_hint_x=.3)); r.add_widget(self.hold)
        r.add_widget(L("السرعة", size_hint_x=.2)); r.add_widget(self.speed)
        r = row()
        for k in ("image", "video", "audio"):
            r.add_widget(B("+ " + KINDS[k], lambda k=k: self.app.choose_media(k, lambda item, k=k: self.set_media(k, item)), BLUE, 44))
        self.mlabel = L("", 30); g.add_widget(self.mlabel)
        self.mprev = Image(size_hint_y=None, height=0); g.add_widget(self.mprev)
        g.add_widget(B("إزالة الوسائط", self.clear_media, GREY, 40))
        g.add_widget(L("معاينة موضع النص: اسحب النص بإصبعك إلى المكان المطلوب", 28))
        self.prev = TextPositionPreview(size_hint_y=None, height=dp(220))
        self.pc = self.prev.bg_color
        g.add_widget(self.prev)
        g.add_widget(B("إعادة النص إلى وسط الشاشة", self.center_text, GREY, 40))
        g.add_widget(B("حفظ كمذكرة", self.save_memo, GREY))
        g.add_widget(B("إرسال واعتماد وعرض", self.do_send, GREEN))
        self.preview()
    def center_text(self): self.prev.set_position(0.10, 0.25); self.preview()
    def set_fg(self, v): self.fgc = v; self.fgb.background_color = H(v); self.preview()
    def set_bg(self, v): self.bgc_ = v; self.bgb.background_color = H(v); self.preview()
    def set_media(self, kind, item):
        self.media["audio" if kind == "audio" else "visual"] = item; self.update_media()
    def clear_media(self): self.media = {"visual": None, "audio": None}; self.update_media()
    def update_media(self):
        parts = []
        for k, lab in (("visual", "المرئي"), ("audio", "الصوت")):
            m = self.media[k]
            if m: parts.append("%s: %s (%s)" % (lab, m.get("name", "")[:18], KINDS.get(m["kind"], "")))
        self.mlabel.text = T("  |  ".join(parts) or "بدون وسائط")
        v = self.media["visual"]
        if v and v["kind"] == "image" and v.get("src") == "local":
            self.mprev.source = v["path"]; self.mprev.height = dp(90)
        else: self.mprev.source = ""; self.mprev.height = 0
    def scene(self):
        try: size = int(self.size_in.text or 48)
        except ValueError: size = 48
        try: hold = int(self.hold.text or 5)
        except ValueError: hold = 5
        raw = self.inp.text
        msgs = [l for l in raw.splitlines() if l.strip()] if self.multi.state == "down" else [raw]
        sc = {"bg": self.bgc_, "text": {"msgs": msgs, "color": self.fgc, "size": size,
              "align": pick(ALIGN, self.align.text, "center"), "mode": pick(MODES, self.mode.text, "static"),
              "tdir": pick(TDIRS, self.tdir.text, "r2l"), "speed": int(self.speed.value), "hold": hold,
              "x": self.prev.position["x"], "y": self.prev.position["y"],
              "w": self.prev.position["w"], "h": self.prev.position["h"]}}
        for k in ("visual", "audio"):
            if self.media[k]: sc[k] = dict(self.media[k])
        return sc
    def preview(self):          # local only, never transmitted
        s = self.scene(); t = s["text"]
        self.pc.rgba = H(s["bg"]); self.prev.label.color = H(t["color"])
        self.prev.label.font_size = "%dsp" % max(12, t["size"] // 2)
        self.prev.label.halign = t["align"]
        self.prev.label.text = T(t["msgs"][0] if t["msgs"] else "اكتب النص ثم اسحبه")
    def save_memo(self):
        sc = self.scene(); body = self.inp.text
        self.app.store.put("memos", {"name": (body.strip()[:20] or "مذكرة"), "body": body, "scene": sc})
        self.app.toast("تم الحفظ (لم يُرسل)")
    def do_send(self): self.app.send_scene(self.scene())

# ---------- Media library ----------
class MediaPage(Page):
    def __init__(self, app):
        super().__init__(app, "media", "استوديو الوسائط")
        r = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
        for k in ("image", "video", "audio"):
            r.add_widget(B("+ " + KINDS[k] + " من الجوال", lambda k=k: app.pick_local(k, lambda p, k=k: (app.add_to_library(p, k), self.refresh())), BLUE))
        self.body.add_widget(r)
        self.lst = scroll_grid(self.body)
    def refresh(self):
        self.lst.clear_widgets()
        for it in self.app.store.items("media", ""):
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
            row.add_widget(L("%s (%s)" % (it["name"][:26], KINDS.get(it["kind"], "")), halign="right"))
            row.add_widget(B("معاينة", lambda i=it: self.preview(i), GREY, 44, 0.3))
            row.add_widget(B("حذف", lambda i=it: self.rm(i), RED, 44, 0.22))
            row.add_widget(B("إرسال", lambda i=it: self.send(i), GREEN, 44, 0.25))
            self.lst.add_widget(row)
    def preview(self, it):
        if it["kind"] == "image":
            popup("معاينة", Image(source=it["path"]), (0.95, 0.8))
        elif it["kind"] == "audio" and self.app.mh:
            self.app.mh.playAudio(it["path"], False); self.app.toast("جاري تشغيل الصوت محلياً")
        else: self.app.toast("معاينة الفيديو تتم بعد الإرسال إلى جهاز العرض")
    def rm(self, it):
        def go():
            try: os.remove(it["path"])
            except OSError: pass
            self.app.store.delete("media", it["id"]); self.refresh()
        confirm("حذف الملف من التطبيق؟", go)
    def send(self, it):
        k = "audio" if it["kind"] == "audio" else "visual"
        sc = {"bg": "#000000", k: {"kind": it["kind"], "src": "local", "path": it["path"], "name": it["name"]}}
        self.app.send_scene(sc, "إرسال «%s» إلى جهاز العرض؟" % it["name"])

# ---------- Screen Designer ----------
class El(Label):
    """Canvas element supporting drag, two-finger scale, rotation and locking."""
    def __init__(self, d, **kw):
        super().__init__(**{**F, **kw}); self.d = d; self.sel = False
        self._touches = {}; self._pinch_base = None; self._angle_base = None
        with self.canvas.before:
            PushMatrix()
            self.rot = Rotate(angle=float(d.get("rotation", 0)), origin=self.center)
            self.bgc = Color(0, 0, 0, 0); self.bgr = Rectangle()
        with self.canvas.after:
            PopMatrix()
        self.bind(pos=self._u, size=self._u); self.apply()
    def _u(self, *a):
        self.bgr.pos, self.bgr.size = self.pos, self.size
        self.text_size = self.size
        self.rot.origin = self.center
    def apply(self):
        d = self.d; live = dyn_text(d); self.text = T(live if live is not None else d.get("text", "")); self.font_size = d.get("size", 32)
        try:
            self.outline_width = int(d.get("outline", 0) or 0); self.outline_color = list(H(d.get("outline_color", "#000000")))
        except Exception: pass
        fg = list(H(d.get("fg", "#FFFFFF"))); fg[3] = max(0.05, min(1.0, float(d.get("opacity", 1.0))))
        self.color = fg
        self.rot.angle = float(d.get("rotation", 0))
        if d.get("bg"):
            c = list(H(d["bg"])); c[3] = max(0.05, min(1.0, float(d.get("bg_opacity", 1.0)))); self.bgc.rgba = c
        else: self.bgc.rgba = (0, 0, 0, 0.15 if self.sel else 0)
    def on_touch_down(self, t):
        if self.collide_point(*t.pos):
            owner = self.parent.owner
            owner.select(self)
            self._touches[t.uid] = t
            t.grab(self)
            if len(self._touches) == 1:
                owner.snap()
            elif len(self._touches) == 2:
                a, b = list(self._touches.values())
                import math
                dist = max(1.0, math.hypot(a.x-b.x, a.y-b.y))
                import math
                angle = math.degrees(math.atan2(b.y-a.y, b.x-a.x))
                self._pinch_base = (dist, self.width, self.height, float(self.d.get("size", 32)))
                self._angle_base = (angle, float(self.d.get("rotation", 0)))
            return True
        return super().on_touch_down(t)
    def on_touch_move(self, t):
        if t.grab_current is self:
            if t.uid in self._touches: self._touches[t.uid] = t
            if len(self._touches) >= 2 and self._pinch_base and not self.d.get("locked"):
                import math
                a, b = list(self._touches.values())[:2]
                dist = max(1.0, math.hypot(a.x-b.x, a.y-b.y))
                base, w, h, font_size = self._pinch_base
                scale = max(0.35, min(4.0, dist/base))
                if self._angle_base:
                    angle = math.degrees(math.atan2(b.y-a.y, b.x-a.x))
                    self.d["rotation"] = (self._angle_base[1] + angle - self._angle_base[0]) % 360
                    self.rot.angle = self.d["rotation"]
                cx, cy = self.center
                self.size = (max(dp(36), w*scale), max(dp(28), h*scale))
                self.center = (cx, cy)
                self.d["size"] = max(10, font_size*scale)
                self.font_size = self.d["size"]
                return True
            if len(self._touches) == 1 and not self.d.get("locked"):
                self.x += t.dx; self.y += t.dy
                return True
        return super().on_touch_move(t)
    def on_touch_up(self, t):
        if t.grab_current is self:
            t.ungrab(self); self._touches.pop(t.uid, None)
            if len(self._touches) < 2:
                self._pinch_base = None; self._angle_base = None
                if not self.d.get("locked") and self.parent:
                    owner = self.parent.owner
                    if owner and owner.area.width > 0 and owner.area.height > 0:
                        gx = owner.area.width * 0.02; gy = owner.area.height * 0.02
                        self.x = owner.area.x + round((self.x-owner.area.x)/gx)*gx
                        self.y = owner.area.y + round((self.y-owner.area.y)/gy)*gy
            return True
        return super().on_touch_up(t)

class Area(FloatLayout):
    pass

class Designer(Page):
    def __init__(self, app):
        super().__init__(app, "designer", "مصمم الشاشة")
        self.cur = None; self.hist = []; self.redo = []
        self.area = Area(size_hint=(1, 1)); self.area.owner = self
        with self.area.canvas.before:
            self.ac = Color(*H(BLUE)); self.ar = Rectangle()
        self.area.bind(pos=self._u, size=self._u)
        self.txt = TI(hint="نص العنصر المحدد", h=40); self.txt.bind(text=self.on_txt)
        r1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for t, cb in (("+ نص", self.add_text), ("+ مربع", self.add_box), ("نسخ", self.dup),
                      ("حذف", self.rm), ("تكبير", lambda: self.fs(6)), ("تصغير", lambda: self.fs(-6)),
                      ("تدوير 15°", lambda: self.rotate(15))):
            r1.add_widget(B(t, cb, GREY, 44))
        r2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for t, cb in (("لون", lambda: self.cyc("fg")), ("خلفية عنصر", lambda: self.cyc("bg")),
                      ("خلفية شاشة", self.cyc_screen), ("للأمام", lambda: self.layer(True)),
                      ("للخلف", lambda: self.layer(False)), ("قفل/فتح", self.toggle_lock),
                      ("إخفاء/إظهار", self.toggle_hidden), ("شفافية -", lambda: self.change_opacity(-0.1)),
                      ("شفافية +", lambda: self.change_opacity(0.1))):
            r2.add_widget(B(t, cb, GREY, 44))
        r3 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for t, cb in (("عرض +", lambda: self.resize(1.10, 1.0)), ("عرض -", lambda: self.resize(0.90, 1.0)),
                      ("ارتفاع +", lambda: self.resize(1.0, 1.10)), ("ارتفاع -", lambda: self.resize(1.0, 0.90)),
                      ("تراجع", self.undo), ("إعادة", self.redo_)):
            r3.add_widget(B(t, cb, GREY, 44))
        r5 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for t, cb in (("+ ساعة", self.add_clock), ("+ تاريخ", self.add_date), ("+ عداد", self.add_countdown),
                      ("ظل", self.toggle_shadow), ("حد", self.cycle_outline), ("تقسيم", self.zones)):
            r5.add_widget(B(t, cb, GREY, 44))
        r4 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
        r4.add_widget(B("حفظ كصفحة", self.save, BLUE)); r4.add_widget(B("حفظ كقالب", lambda: self.save("templates"), BLUE))
        r4.add_widget(B("إرسال واعتماد", self.do_send, GREEN))
        for w in (self.area, self.txt, r1, r2, r3, r5, r4): self.body.add_widget(w)
        self.bgcol = "#1565C0"; self.pal = list(COLORS.values()); self._zi = 0
        Clock.schedule_interval(self.tick_live, 1)
    def _u(self, *a): self.ar.pos, self.ar.size = self.area.pos, self.area.size
    def snap(self): self.hist.append(self.dump()); self.redo = []; self.hist = self.hist[-30:]
    def dump(self):
        w, h = self.area.size; x0, y0 = self.area.pos
        return {"bg": self.bgcol, "els": [{**e.d, "x": (e.x - x0) / w, "y": (e.y - y0) / h, "w": e.width / w,
                                          "h": e.height / h, "size": e.d.get("size", 32) / h,
                                          "rotation": float(e.d.get("rotation", 0)), "locked": bool(e.d.get("locked", False))}
                                         for e in self.area.children[::-1] if isinstance(e, El)]}
    def load(self, design):
        self.area.clear_widgets(); self.cur = None
        self.bgcol = design.get("bg", "#1565C0"); self.ac.rgba = H(self.bgcol)
        w, h = self.area.size; x0, y0 = self.area.pos
        for d in design.get("els", []):
            d = dict(d); d["size"] = d.get("size", 0.05) * h
            e = El(d, size_hint=(None, None), size=(d["w"] * w, d["h"] * h), pos=(x0 + d["x"] * w, y0 + d["y"] * h))
            if d.get("hidden"): e.opacity = 0
            self.area.add_widget(e)
    def add(self, d):
        self.snap(); w, h = self.area.size
        e = El(d, size_hint=(None, None), size=(w * 0.6, h * 0.12), pos=(self.area.x + w * .2, self.area.y + h * .4))
        self.area.add_widget(e); self.select(e)
    def tick_live(self, dt):
        for e in self.area.children:
            if isinstance(e, El) and dyn_text(e.d) is not None: e.apply()
    def add_clock(self): self.add({"text": "", "k": "clock", "size": 48, "fg": "#FFFFFF"})
    def add_date(self): self.add({"text": "", "k": "date", "size": 40, "fg": "#FFFFFF"})
    def add_countdown(self):
        target = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 3600))
        self.add({"text": target, "k": "countdown", "size": 48, "fg": "#FFFFFF"})
        self.app.toast("عدّل نص العنصر ليكون موعد النهاية: سنة-شهر-يوم ساعة:دقيقة")
    def toggle_shadow(self):
        if self.cur:
            self.snap(); self.cur.d["shadow"] = not bool(self.cur.d.get("shadow")); self.cur.apply()
            self.app.toast("الظل يظهر على جهاز العرض" if self.cur.d["shadow"] else "تم إلغاء الظل")
    def cycle_outline(self):
        if self.cur:
            self.snap(); w = int(self.cur.d.get("outline", 0) or 0); self.cur.d["outline"] = {0: 2, 2: 4, 4: 0}.get(w, 0)
            self.cur.d.setdefault("outline_color", "#000000"); self.cur.apply()
    def zones(self):
        box = BoxLayout(orientation="vertical", spacing=dp(5), padding=dp(6))
        p = popup("اختر تخطيط تقسيم الشاشة", box, (0.92, 0.82))
        g = scroll_grid(box)
        for name, cells in ZONE_SETS:
            g.add_widget(B("%s (%d مناطق)" % (name, len(cells)),
                           lambda name=name, cells=cells: (p.dismiss(), self._apply_zones(name, cells)), BLUE, 48))
        box.add_widget(B("إلغاء", p.dismiss, GREY))

    def _apply_zones(self, name, cells):
        def apply():
            self.snap()
            self.area.clear_widgets(); self.cur = None
            w, h = self.area.size; x0, y0 = self.area.pos
            for n, (cx, cy, cw, ch) in enumerate(cells):
                d = {"text": "منطقة %d" % (n + 1), "size": 28, "fg": "#FFFFFF",
                     "bg": self.pal[(n * 2 + 1) % len(self.pal)], "bg_opacity": 0.9}
                e = El(d, size_hint=(None, None),
                       size=(max(dp(36), cw * w * .98), max(dp(28), ch * h * .98)),
                       pos=(x0 + cx * w + cw * w * .01, y0 + cy * h + ch * h * .01))
                self.area.add_widget(e)
            self.app.toast("تم تطبيق تقسيم الشاشة: " + name + " — عدّل كل منطقة باللمس")
        if any(isinstance(x, El) for x in self.area.children):
            confirm("سيستبدل قالب التقسيم العناصر الحالية في مساحة التصميم. هل تريد المتابعة؟", apply)
        else:
            apply()
    def add_text(self): self.add({"text": "نص جديد", "size": 32, "fg": "#FFFFFF"})
    def add_box(self): self.add({"text": "", "size": 20, "fg": "#FFFFFF", "bg": "#000000"})
    def select(self, e):
        if self.cur: self.cur.sel = False; self.cur.apply()
        self.cur = e; e.sel = True; e.apply(); self.txt.unbind(text=self.on_txt)
        self.txt.text = e.d.get("text", ""); self.txt.bind(text=self.on_txt)
    def on_txt(self, i, v):
        if self.cur: self.cur.d["text"] = v; self.cur.apply()
    def fs(self, n):
        if self.cur: self.snap(); self.cur.d["size"] = max(10, self.cur.d.get("size", 32) + n); self.cur.apply()
    def cyc(self, k):
        if not self.cur: return
        self.snap(); cur = self.cur.d.get(k); i = self.pal.index(cur) if cur in self.pal else -1
        self.cur.d[k] = self.pal[(i + 1) % len(self.pal)]; self.cur.apply()
    def cyc_screen(self):
        self.snap(); i = self.pal.index(self.bgcol) if self.bgcol in self.pal else -1
        self.bgcol = self.pal[(i + 1) % len(self.pal)]; self.ac.rgba = H(self.bgcol)
    def dup(self):
        if self.cur:
            d = dict(self.cur.d); self.add(d); self.cur.x += dp(15); self.cur.y -= dp(15)
    def rm(self):
        if self.cur: self.snap(); self.area.remove_widget(self.cur); self.cur = None
    def rotate(self, degrees):
        if self.cur:
            self.snap(); self.cur.d["rotation"] = (float(self.cur.d.get("rotation", 0)) + degrees) % 360
            self.cur.apply()
    def resize(self, sx, sy):
        if self.cur and not self.cur.d.get("locked"):
            self.snap(); self.cur.size = (max(dp(36), self.cur.width*sx), max(dp(28), self.cur.height*sy))
    def layer(self, front=True):
        if not self.cur: return
        self.snap(); e = self.cur; self.area.remove_widget(e)
        self.area.add_widget(e, index=0 if front else len(self.area.children))
        self.select(e)
    def change_opacity(self, delta):
        if self.cur:
            self.snap(); self.cur.d["opacity"] = max(0.05, min(1.0, float(self.cur.d.get("opacity", 1.0)) + delta)); self.cur.apply()
    def toggle_hidden(self):
        if self.cur:
            self.snap(); self.cur.d["hidden"] = not bool(self.cur.d.get("hidden", False))
            self.cur.opacity = 0 if self.cur.d["hidden"] else 1
            self.app.toast("تم إخفاء العنصر" if self.cur.d["hidden"] else "تم إظهار العنصر")
    def toggle_lock(self):
        if self.cur:
            self.snap(); self.cur.d["locked"] = not bool(self.cur.d.get("locked")); self.cur.apply()
            self.app.toast("تم قفل العنصر" if self.cur.d["locked"] else "تم فتح العنصر")
    def undo(self):
        if self.hist: self.redo.append(self.dump()); self.load(self.hist.pop())
    def redo_(self):
        if self.redo: self.hist.append(self.dump()); self.load(self.redo.pop())
    def save(self, col="pages"):
        d = self.dump(); item = {"name": "تصميم " + time.strftime("%H:%M:%S"), "body": json.dumps(d, ensure_ascii=False)}
        self.app.store.put(col, item); self.app.toast("تم الحفظ (لم يُرسل)")
    def do_send(self):
        d = self.dump(); confirm("سيتم استبدال المعروض على جهاز العرض. متابعة؟", lambda: self.app.send("apply_design", d))

# ---------- Projects ----------
class ProjectEditor(Page):
    def __init__(self, app):
        super().__init__(app, "project_edit", "محرر المشروع")
        self.p = None
        self.name_l = L("", 30); self.body.add_widget(self.name_l)
        self.lst = scroll_grid(self.body)
        self.body.add_widget(B("+ إضافة المشهد الحالي من استوديو النصوص", self.add_scene, BLUE))
        r = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
        r.add_widget(B("تجهيز على جهاز العرض (بدون عرض)", lambda: self.stage(), GREY))
        r.add_widget(B("تشغيل المشروع", self.play, GREEN))
        self.body.add_widget(r)
    def open(self, proj):
        self.p = copy.deepcopy(proj); self.p.setdefault("scenes", []); self.app.go("project_edit")
    def save(self): self.p = self.app.store.put("projects", self.p)
    def refresh(self):
        self.lst.clear_widgets()
        if not self.p: return
        self.name_l.text = T("المشروع: %s  (%d مشهد)" % (self.p.get("name", ""), len(self.p["scenes"])))
        for i, sc in enumerate(self.p["scenes"]):
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
            row.add_widget(L("%d. %s" % (i + 1, summary(sc)), halign="right"))
            row.add_widget(B("↑", lambda i=i: self.move(i, -1), GREY, 44, 0.12))
            row.add_widget(B("↓", lambda i=i: self.move(i, 1), GREY, 44, 0.12))
            row.add_widget(B("حذف", lambda i=i: self.rm(i), RED, 44, 0.2))
            self.lst.add_widget(row)
    def add_scene(self):
        sc = self.app.sm.get_screen("text").scene()
        has_text = any(str(m).strip() for m in sc["text"]["msgs"])
        if not has_text and not sc.get("visual") and not sc.get("audio"):
            return self.app.toast("اكتب نصاً أو أضف وسائط في الاستوديو أولاً")
        self.p["scenes"].append(sc); self.save(); self.refresh()
    def move(self, i, d):
        j = i + d; s = self.p["scenes"]
        if 0 <= j < len(s): s[i], s[j] = s[j], s[i]; self.save(); self.refresh()
    def rm(self, i): self.p["scenes"].pop(i); self.save(); self.refresh()
    def stage(self, then=None):
        if not self.app.is_ready(): return self.app.toast("اتصل بجهاز العرض أولاً")
        if not self.p["scenes"]: return self.app.toast("المشروع فارغ")
        self.app.toast("جاري التجهيز...")
        def go(res):
            self.app.send("store_project", {"id": self.p["id"], "name": self.p.get("name", ""), "scenes": res,
                                            "secs": int(self.p.get("secs") or 10)})
            if then: then()
        self.app.resolve_scenes(self.p["scenes"], go, self.app.toast)
    def play(self):
        confirm("سيتم عرض المشروع على جهاز العرض واستبدال المعروض. متابعة؟",
                lambda: self.stage(then=lambda: self.app.send("play_project", {"id": self.p["id"]})))

# ---------- text command center ----------
class CommandCenter(Page):
    def __init__(self, app):
        super().__init__(app, "commands", "مركز أوامر جهاز العرض")
        self.body.add_widget(L("اكتب أمراً بالعربية أو الإنجليزية. يتم البحث والتشغيل داخل جهاز Receiver دون نسخ ملفات الصوت والفيديو.", 76))
        self.input = TI(hint="مثال: شغل فيديو الترحيب", ml=True, h=92)
        self.body.add_widget(self.input)
        self.result = L("أمثلة: اعرض آخر صورة | شغل صوت الموسيقى | اعرض صور السيارة | احصائيات المكتبة", 72)
        self.body.add_widget(self.result)
        self.body.add_widget(B("تنفيذ الأمر", self.execute, GREEN))
        self.body.add_widget(B("تحديث فهرس مكتبة المستقبل", lambda: self.send_text("تحديث المكتبة"), BLUE))
        examples = ["اعرض آخر صورة", "شغل آخر فيديو", "شغل آخر صوت", "احصائيات المكتبة", "اوقف العرض", "استعد العرض"]
        for ex in examples:
            self.body.add_widget(B(ex, lambda ex=ex: self.send_text(ex), GREY, 42))

    def execute(self):
        text = self.input.text.strip()
        if not text: return self.app.toast("اكتب الأمر أولاً")
        self.send_text(text)

    def send_text(self, text):
        if self.app.send("command", {"text": text}):
            self.result.text = T("تم إرسال الأمر: " + text)


# ---------- other pages ----------
class Remote(Page):
    def __init__(self, app):
        super().__init__(app, "remote", "التحكم عن بعد")
        cmds = [("إخفاء المحتوى", "hide"), ("استعادة آخر عرض", "restore"), ("مسح الشاشة", "clear"),
                ("اختبار اتصال", "ping"), ("إعادة تحميل المعتمد", "reload"),
                ("التالي", "next"), ("السابق", "prev"), ("إيقاف الطوارئ", "emergency_off")]
        g = scroll_grid(self.body)
        for t, ty in cmds:
            g.add_widget(B(t, lambda ty=ty, t=t: confirm(t + "؟", lambda: app.send(ty, {})),
                           RED if ty == "clear" else GREY))
        g.add_widget(L("سطوع شاشة جهاز العرض", 24))
        self.br = Slider(min=0.05, max=1.0, value=1.0, size_hint_y=None, height=dp(44)); self._brev = None
        def br_changed(i, v):
            if self._brev: self._brev.cancel()
            self._brev = Clock.schedule_once(lambda dt: app.send("brightness", {"level": round(v, 2)}), 0.5)
        self.br.bind(value=br_changed); g.add_widget(self.br)
        g.add_widget(B("سطوع تلقائي (حسب النظام)", lambda: app.send("brightness", {"level": -1}), GREY))
        g.add_widget(L("انتقال المشاهد", 24))
        self.tr = SP(T("بدون"), [T(k) for k in TRANS])
        self.tr.bind(text=lambda i, v: app.send("transition", {"mode": next((m for k, m in TRANS.items() if T(k) == v), "none")}))
        g.add_widget(self.tr)
        self.em = TI(hint="نص رسالة الطوارئ"); g.add_widget(self.em)
        g.add_widget(B("إرسال رسالة طوارئ", lambda: confirm("استبدال العرض برسالة الطوارئ؟",
            lambda: app.send("emergency", {"text": self.em.text, "color": "#FFFFFF", "bg": "#B71C1C",
                                           "size": 64, "seconds": 0})), RED))

class Devices(Page):
    def __init__(self, app):
        super().__init__(app, "devices", "إدارة الأجهزة")
        self.info = L("", 60)
        self.body.add_widget(self.info)
        self.body.add_widget(B("بحث واتصال", app.connect, BLUE)); self.body.add_widget(B("قطع الاتصال", app.disconnect, GREY))
        self.auto = B("", app.toggle_auto, GREY); self.body.add_widget(self.auto)
        self.body.add_widget(B("اقتران آمن (تشفير)", app.start_pairing, BLUE)); self.body.add_widget(B("إلغاء الاقتران", app.unpair, GREY))
        self.body.add_widget(B("حالة جهاز العرض (البطارية والمساحة)", lambda: app.send("status", {}), GREY))
        self.logv = Label(**F, color=(1, 1, 1, 1), halign="right", valign="top", size_hint_y=None)
        self.logv.bind(texture_size=lambda i, v: setattr(i, "height", v[1]),
                       width=lambda i, v: setattr(i, "text_size", (v, None)))
        sv = ScrollView(); sv.add_widget(self.logv); self.body.add_widget(sv)
    def refresh(self):
        wifi = ("واي فاي جهاز العرض: " + self.app.rinfo["ip"]) if self.app.rinfo else "واي فاي: غير معروف بعد"
        link = "مشفّر ✔" if self.app.sec.sess else "مفتوح (غير مقترن)"
        self.info.text = T("الحالة: " + self.app.status_text() + "  |  الاقتران: " + link + "\n" + wifi)
        self.auto.text = T("اتصال تلقائي عند الفتح: " + ("تشغيل" if self.app.store.d["settings"].get("auto_connect") else "إيقاف"))
        self.logv.text = "\n".join(T(x["t"][11:] + " " + x["m"]) for x in self.app.store.d["log"][-40:][::-1])

class Fonts(Page):
    def __init__(self, app):
        super().__init__(app, "fonts", "مكتبة الخطوط")
        self.v = L("", halign="right"); self.body.add_widget(self.v)
        self.path = TI(hint="مسار ملف الخط (ttf أو otf)"); self.body.add_widget(self.path)
        self.body.add_widget(B("استيراد خط", self.imp, BLUE))
        self.body.add_widget(B("حذف الخطوط المستوردة", self.clear, RED))
    def refresh(self): self.v.text = T("الخطوط: " + "، ".join(sorted(self.app.fonts)) or "لا يوجد")
    def imp(self):
        p = self.path.text.strip()
        try:
            shutil.copy(p, self.app.fdir); self.app.scan_fonts(); self.refresh(); self.app.toast("تم الاستيراد")
        except Exception as e: self.app.toast("فشل: %s" % e)
    def clear(self):
        for f in glob.glob(os.path.join(self.app.fdir, "*")): os.remove(f)
        self.app.scan_fonts(); self.refresh()

class Backup(Page):
    def __init__(self, app):
        super().__init__(app, "backup", "النسخ الاحتياطي")
        self.v = L(""); self.body.add_widget(self.v)
        self.body.add_widget(B("نسخ احتياطي الآن", self.backup, BLUE))
        self.path = TI(hint="مسار ملف نسخة للاستعادة"); self.body.add_widget(self.path)
        self.body.add_widget(B("استعادة", self.restore, GREY))
    def backup(self):
        name = "ble-remote-%s.json" % time.strftime("%Y%m%d-%H%M%S")
        p = os.path.join(self.app.bdir, name); self.app.store.export_to(p); msg = p
        try: d = "/sdcard/Download/" + name; shutil.copy(p, d); msg = d
        except Exception: pass
        self.v.text = T("تم: " + msg); self.path.text = msg
    def restore(self):
        try: self.app.store.import_from(self.path.text.strip()); self.v.text = T("تمت الاستعادة")
        except Exception as e: self.v.text = T("فشل: %s" % e)

class ContentHub(Page):
    """One entry point for the local and Receiver-side content libraries."""
    def __init__(self, app):
        super().__init__(app, "content", "مدير المحتوى المتقدم")
        self.stats = L("", 54, halign="right")
        self.body.add_widget(self.stats)
        g = scroll_grid(self.body)
        entries = [
            ("مكتبة وسائط الهاتف", "media", BLUE), ("مكتبة جهاز العرض", "rbrowser", BLUE),
            ("مدير ملفات المستقبل", "files", GREY), ("المشاريع", "projects", GREY),
            ("قوائم التشغيل", "playlists", GREY), ("المشاهد المحفوظة", "scenes_v8", GREY),
            ("الصفحات والتصاميم", "pages", GREY), ("القوالب", "tplv8", GREY),
            ("الجدولة", "sched", GREY), ("النسخ الاحتياطي", "backup", GREY),
        ]
        for title, target, color in entries:
            g.add_widget(B(title, lambda target=target: app.go(target), color, 48))
    def refresh(self):
        d = self.app.store.d
        self.stats.text = T("مكتبة الهاتف: %d وسائط  |  مشاهد: %d  |  مشاريع: %d  |  قوائم تشغيل: %d" %
                            (len(d.get("media", [])), len(d.get("scenes", [])),
                             len(d.get("projects", [])), len(d.get("playlists", []))))


class TextHub(Page):
    """Text editing, reusable snippets, news tickers and font management."""
    def __init__(self, app):
        super().__init__(app, "text_manager", "إدارة النصوص")
        self.body.add_widget(L("إدارة النصوص الثابتة والمتحركة والرسائل المحفوظة والخطوط العربية.", 58))
        for title, target, color in (("محرر النصوص", "text", BLUE), ("استوديو النصوص والأخبار", "news", BLUE),
                                     ("المذكرات والنصوص المحفوظة", "memos", GREY), ("مكتبة الخطوط", "fonts", GREY)):
            self.body.add_widget(B(title, lambda target=target: app.go(target), color, 50))


class DesignHub(Page):
    """Entry point for design canvas, layered studio, layouts and templates."""
    def __init__(self, app):
        super().__init__(app, "design_hub", "استديو التصميم")
        self.body.add_widget(L("أنشئ تصميماً بالسحب والإفلات، أو استخدم الطبقات والقوالب الجاهزة.", 58))
        self.body.add_widget(B("تقسيم الشاشة — محتوى مستقل لكل منطقة", lambda: app.go("zones"), GREEN, 50))
        for title, target, color in (("مصمم الشاشة بالسحب والإفلات", "designer", BLUE),
                                     ("استوديو الطبقات والنصوص المتحركة", "news", BLUE),
                                     ("قوالب التصميم والأخبار", "tplv8", GREY),
                                     ("المشاهد المحفوظة", "scenes_v8", GREY),
                                     ("المشاريع", "projects", GREY)):
            self.body.add_widget(B(title, lambda target=target: app.go(target), color, 50))
        self.body.add_widget(L("داخل مصمم الشاشة ستجد أداة «تقسيم» مع قوالب متعددة للمناطق.", 48))
    def open_split(self):
        self.app.go("designer")
        Clock.schedule_once(lambda *_: self.app.designer.zones(), 0.25)


class EmergencyPage(Page):
    """Emergency overlay controls, with local presets and explicit confirmation before send."""
    PRESETS = {
        "إخلاء فوري": ("يرجى إخلاء المكان بهدوء واتباع تعليمات المسؤولين", "#FFFFFF", "#B71C1C"),
        "تنبيه عام": ("تنبيه مهم — يرجى الانتباه للتعليمات", "#FFFFFF", "#8E0000"),
        "انتهاء الحالة": ("انتهت حالة الطوارئ — يمكن استئناف العرض", "#FFFFFF", "#1B5E20"),
    }
    def __init__(self, app):
        super().__init__(app, "emergency", "وضع الطوارئ")
        self.msg = TI(hint="اكتب رسالة الطوارئ", ml=True, h=100)
        self.fg = "#FFFFFF"; self.bg = "#B71C1C"
        self.seconds = SP(T("حتى الإيقاف اليدوي"), [T(x) for x in ("حتى الإيقاف اليدوي", "10 ثوانٍ", "30 ثانية", "60 ثانية", "5 دقائق")])
        self.preview = L("معاينة رسالة الطوارئ", 76, font_size="22sp")
        with self.preview.canvas.before:
            self.preview_bg_color = Color(*H(self.bg))
            self.preview_bg_rect = Rectangle(pos=self.preview.pos, size=self.preview.size)
        self.preview.bind(pos=self._sync_preview_rect, size=self._sync_preview_rect)
        self.body.add_widget(L("تظهر رسالة الطوارئ فوق العرض الحالي على جهاز المستقبل. الإرسال يتطلب تأكيداً.", 58))
        self.body.add_widget(self.msg); self.msg.bind(text=lambda *_: self.update_preview())
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4))
        self.fgb = B("لون النص", lambda: pick_color("لون نص الطوارئ", self.fg, self.set_fg), GREY)
        self.bgb = B("خلفية الطوارئ", lambda: pick_color("خلفية الطوارئ", self.bg, self.set_bg), RED)
        row.add_widget(self.fgb); row.add_widget(self.bgb); self.body.add_widget(row)
        self.body.add_widget(self.seconds); self.body.add_widget(self.preview)
        for title in self.PRESETS:
            self.body.add_widget(B(title, lambda title=title: self.use_preset(title), GREY, 42))
        self.body.add_widget(B("إرسال وضع الطوارئ", self.send_alert, RED, 54))
        self.body.add_widget(B("إيقاف الطوارئ واستعادة التحكم", self.stop_alert, GREEN, 50))
        self.body.add_widget(B("حفظ الرسالة ضمن القوالب", self.save_alert, BLUE, 46))
        self.saved = scroll_grid(self.body)
        self.body.add_widget(L("رسائل محفوظة", 30))
    def set_fg(self, value): self.fg = value; self.fgb.background_color = H(value); self.update_preview()
    def set_bg(self, value): self.bg = value; self.bgb.background_color = H(value); self.update_preview()
    def update_preview(self):
        self.preview.text = T(self.msg.text.strip() or "معاينة رسالة الطوارئ")
        self.preview.color = H(self.fg)
        self.preview_bg_color.rgba = H(self.bg)
    def _sync_preview_rect(self, widget, *_):
        self.preview_bg_rect.pos = widget.pos
        self.preview_bg_rect.size = widget.size
    def use_preset(self, title):
        text, fg, bg = self.PRESETS[title]
        self.msg.text = text; self.fg = fg; self.bg = bg
        self.fgb.background_color = H(fg); self.bgb.background_color = H(bg); self.update_preview()
    def _seconds(self):
        value = self.seconds.text
        return next((secs for label, secs in (("حتى الإيقاف اليدوي", 0), ("10 ثوانٍ", 10),
                     ("30 ثانية", 30), ("60 ثانية", 60), ("5 دقائق", 300)) if T(label) == value), 0)
    def send_alert(self):
        text = self.msg.text.strip()
        if not text: return self.app.toast("اكتب رسالة الطوارئ أولاً")
        payload = {"text": text, "color": self.fg, "bg": self.bg, "size": 64, "seconds": self._seconds()}
        confirm("سيتم استبدال العرض الحالي برسالة الطوارئ. هل تريد الإرسال؟",
                lambda: self.app.send("emergency", payload))
    def stop_alert(self):
        confirm("إيقاف رسالة الطوارئ على جهاز المستقبل؟",
                lambda: self.app.send("emergency_off", {}))
    def save_alert(self):
        text = self.msg.text.strip()
        if not text: return self.app.toast("اكتب رسالة قبل الحفظ")
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        name = TI("رسالة طوارئ " + time.strftime("%H:%M"), h=44); box.add_widget(name)
        p = popup("حفظ قالب الطوارئ", box, (0.9, 0.42))
        def save():
            self.app.store.put("alerts", {"name": name.text.strip() or "رسالة طوارئ", "text": text,
                "color": self.fg, "bg": self.bg, "seconds": self._seconds()})
            p.dismiss(); self.refresh(); self.app.toast("تم حفظ قالب الطوارئ")
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        row.add_widget(B("إلغاء", p.dismiss, GREY)); row.add_widget(B("حفظ", save, GREEN)); box.add_widget(row)
    def refresh(self):
        self.saved.clear_widgets()
        for item in self.app.store.items("alerts"):
            row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(3))
            row.add_widget(L(item.get("name", "رسالة")[:24], halign="right"))
            row.add_widget(B("تحميل", lambda item=item: self.load_alert(item), BLUE, 42, .24))
            row.add_widget(B("حذف", lambda item=item: self.delete_alert(item), RED, 42, .2))
            self.saved.add_widget(row)
    def load_alert(self, item):
        self.msg.text = item.get("text", ""); self.fg = item.get("color", "#FFFFFF"); self.bg = item.get("bg", "#B71C1C")
        self.fgb.background_color = H(self.fg); self.bgb.background_color = H(self.bg)
        secs = int(item.get("seconds", 0) or 0)
        self.seconds.text = T({0: "حتى الإيقاف اليدوي", 10: "10 ثوانٍ", 30: "30 ثانية", 60: "60 ثانية", 300: "5 دقائق"}.get(secs, "حتى الإيقاف اليدوي"))
        self.update_preview()
    def delete_alert(self, item):
        confirm("حذف قالب الطوارئ؟", lambda: (self.app.store.delete("alerts", item["id"]), self.refresh()))


class Settings(Page):
    BG_CHOICES = {"كحلي داكن": "#0B0F1A", "رمادي فحمي": "#171923", "أزرق ليلي": "#10243A", "أخضر داكن": "#102820"}
    ACCENT_CHOICES = {"أزرق": "#1565C0", "فيروزي": "#00897B", "بنفسجي": "#6A1B9A", "برتقالي": "#EF6C00"}
    def __init__(self, app):
        super().__init__(app, "settings", "الإعدادات وتخصيص الواجهة")
        s = app.store.d["settings"]
        self.body.add_widget(L("تخصيص مظهر WALIBRA", 32))
        self.bg_sp = SP(T(next((k for k, v in self.BG_CHOICES.items() if v == s.get("ui_bg")), "كحلي داكن")),
                        [T(k) for k in self.BG_CHOICES])
        self.accent_sp = SP(T(next((k for k, v in self.ACCENT_CHOICES.items() if v == s.get("ui_accent")), "أزرق")),
                            [T(k) for k in self.ACCENT_CHOICES])
        self.body.add_widget(L("لون خلفية التطبيق", 24)); self.body.add_widget(self.bg_sp)
        self.body.add_widget(L("اللون الرئيسي للأزرار", 24)); self.body.add_widget(self.accent_sp)
        self.body.add_widget(B("تطبيق المظهر وحفظه", self.apply_theme, BLUE))
        self.body.add_widget(B("تغيير خلفية التطبيق من معرض الجوال", lambda: app.pick_local("image", app.set_bg), BLUE))
        self.body.add_widget(B("إزالة خلفية التطبيق", lambda: app.set_bg(""), GREY))
        self.pin = TI(hint="رمز سري جديد (اتركه فارغاً للإلغاء)", password=True); self.body.add_widget(self.pin)
        self.body.add_widget(B("حفظ الرمز السري", self.save_pin, BLUE))
        self.body.add_widget(L("الواجهة عربية من اليمين إلى اليسار. تغيير الخلفية والصورة واللون الرئيسي يُحفظ على الجهاز.", 54))
    def apply_theme(self):
        bg = next((v for k, v in self.BG_CHOICES.items() if T(k) == self.bg_sp.text), self.BG_CHOICES["كحلي داكن"])
        accent = next((v for k, v in self.ACCENT_CHOICES.items() if T(k) == self.accent_sp.text), self.ACCENT_CHOICES["أزرق"])
        self.app.store.d["settings"].update({"ui_bg": bg, "ui_accent": accent}); self.app.store.save()
        self.app.apply_appearance(); self.app.toast("تم حفظ مظهر الواجهة")
    def save_pin(self):
        p = self.pin.text; s = self.app.store.d["settings"]
        s["pin"] = hashlib.sha256(p.encode()).hexdigest() if p else ""
        self.app.store.save(); self.app.toast("تم حفظ إعداد الرمز السري")

class FileManager(Page):
    """Browse, rename and delete files stored on the Receiver; shows free space."""
    def __init__(self, app):
        super().__init__(app, "files", "مدير ملفات جهاز العرض")
        self.info = L("", 44); self.body.add_widget(self.info)
        self.lst = scroll_grid(self.body)
        self.body.add_widget(B("تحديث القائمة", self.refresh, BLUE))
    def refresh(self):
        if not self.app.rinfo:
            self.info.text = T("اتصل بجهاز العرض أولاً (وعلى نفس شبكة الواي فاي)"); return
        def run():
            try: st, d = self.app.rcall("GET", "/files")
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self.info, "text", T("تعذر الاتصال: %s" % e)), 0); return
            Clock.schedule_once(lambda dt: self.show(d), 0)
        threading.Thread(target=run, daemon=True).start()
    def show(self, d):
        files = d.get("files", [])
        used = sum(f["size"] for f in files)
        self.info.text = T("الملفات: %d | المستخدم: %s | المتاح: %s" % (len(files), human(used), human(d.get("free", 0))))
        self.lst.clear_widgets()
        for f in files:
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
            row.add_widget(L("%s  (%s)%s" % (f["name"][:28], human(f["size"]), "  ناقص" if f.get("partial") else ""), halign="right"))
            row.add_widget(B("تسمية", lambda n=f["name"]: self.rename(n), GREY, 44, 0.3))
            row.add_widget(B("حذف", lambda n=f["name"]: confirm("حذف «%s» من جهاز العرض نهائياً؟" % n, lambda: self.act("/delete?name=" + quote(n))), RED, 44, 0.25))
            self.lst.add_widget(row)
    def act(self, path):
        def run():
            try: st, d = self.app.rcall("POST", path); msg = "تم" if st == 200 else "فشل: %s" % d.get("error", st)
            except Exception as e: msg = "فشل: %s" % e
            Clock.schedule_once(lambda dt: (self.app.toast(msg), self.refresh()), 0)
        threading.Thread(target=run, daemon=True).start()
    def rename(self, old):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        ti = TI(old); box.add_widget(ti)
        p = popup("اسم جديد", box, (0.9, 0.4))
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        row.add_widget(B("إلغاء", p.dismiss, GREY))
        row.add_widget(B("حفظ", lambda: (p.dismiss(), self.act("/rename?old=%s&new=%s" % (quote(old), quote(ti.text.strip() or old)))), GREEN))
        box.add_widget(row)

class Pad(Widget):
    """Touch pad: swipe = next/previous or brightness, double tap = hide/restore."""
    def __init__(self, app, **kw):
        super().__init__(**kw); self.app = app; self.start = None; self.last_tap = 0.0
        with self.canvas:
            Color(0.08, 0.14, 0.25, 1); self.r = Rectangle()
        self.bind(pos=lambda i, v: setattr(self.r, "pos", v), size=lambda i, v: setattr(self.r, "size", v))
    def on_touch_down(self, t):
        if self.collide_point(*t.pos): t.grab(self); self.start = (t.x, t.y, time.time()); return True
    def on_touch_up(self, t):
        if t.grab_current is not self or not self.start: return False
        t.ungrab(self); x0, y0, t0 = self.start; self.start = None
        dx, dy, dt = t.x - x0, t.y - y0, time.time() - t0
        a = self.app
        if abs(dx) > dp(70) and abs(dx) > abs(dy) * 1.5: a.send("next" if dx < 0 else "prev", {})
        elif abs(dy) > dp(70) and abs(dy) > abs(dx) * 1.5:
            a.level = max(0.05, min(1.0, a.level + (0.15 if dy > 0 else -0.15)))
            a.send("brightness", {"level": round(a.level, 2)})
        elif abs(dx) < dp(15) and abs(dy) < dp(15) and dt < 0.35:
            now = time.time()
            if now - self.last_tap < 0.45:
                a.pad_hidden = not a.pad_hidden; self.last_tap = 0.0
                a.send("hide" if a.pad_hidden else "restore", {})
            else: self.last_tap = now
        return True

class GesturePad(Page):
    def __init__(self, app):
        super().__init__(app, "pad", "لوحة الإيماءات")
        self.body.add_widget(L("اسحب لليسار: التالي  |  لليمين: السابق\nلأعلى/لأسفل: السطوع  |  نقرتان: إخفاء/إظهار", 60))
        self.body.add_widget(Pad(app, size_hint=(1, 1)))

class ReceiverBrowser(Page):
    """Browse the Receiver's own photos/videos/audio (original files, nothing copied), play them,
    control playback, and build playlists from them."""
    def __init__(self, app):
        super().__init__(app, "rbrowser", "متصفح جهاز العرض")
        self.items = []; self.kind = "image"; self.sel = {}; self.repeat = False; self.cover = False
        r0 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        self.kinds = {"صور": "image", "فيديو": "video", "صوت": "audio"}
        self.ks = SP(T("صور"), [T(k) for k in self.kinds], size_hint_x=.28)
        self.ks.bind(text=lambda i, v: self.set_kind(v))
        self.q = TI(hint="بحث بالاسم"); self.q.bind(text=lambda *_: self.show())
        r0.add_widget(self.ks); r0.add_widget(self.q); r0.add_widget(B("تحديث", self.load, BLUE, 44, 0.22))
        self.cnt = L("", 24); self.lst = scroll_grid(self.body)
        self.body.add_widget(r0); self.body.add_widget(self.cnt)
        # playback panel
        self.state = L("لا يوجد تشغيل", 28)
        r1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for t, cb in (("السابق", lambda: app.send("prev", {})), ("-10ث", lambda: self.ctl("seek", -10000)),
                      ("تشغيل/إيقاف مؤقت", lambda: self.ctl("toggle")), ("+10ث", lambda: self.ctl("seek", 10000)),
                      ("التالي", lambda: app.send("next", {}))):
            r1.add_widget(B(t, cb, GREY, 44))
        r2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        self.vol = Slider(min=0, max=100, value=50); self._vev = None
        def vol_changed(i, v):
            if self._vev: self._vev.cancel()
            self._vev = Clock.schedule_once(lambda dt: self.ctl("volume", int(v)), 0.4)
        self.vol.bind(value=vol_changed)
        r2.add_widget(L("الصوت")); r2.add_widget(self.vol)
        r2.add_widget(B("إيقاف الوسائط", lambda: app.send("command", {"text": "اوقف الوسائط"}), RED, 44, 0.35))
        # selection / playlist row
        r3 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        self.secs = TI("10", hint="ثواني للصور", input_filter="int", h=44, size_hint_x=.22)
        self.rep = ToggleButton(text=T("تكرار"), size_hint_x=.2, **F); self.rep.bind(state=lambda i, v: setattr(self, "repeat", v == "down"))
        self.fit = ToggleButton(text=T("ملء الشاشة"), size_hint_x=.3, **F); self.fit.bind(state=lambda i, v: setattr(self, "cover", v == "down"))
        r3.add_widget(self.secs); r3.add_widget(self.rep); r3.add_widget(self.fit)
        r4 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
        r4.add_widget(B("تشغيل المحدد كقائمة", self.play_selected, GREEN)); r4.add_widget(B("حفظ كمشروع", self.save_selected, BLUE))
        for w in (self.state, r1, r2, r3, r4): self.body.add_widget(w)
        Clock.schedule_interval(self.poll_state, 2.0)
    def on_pre_enter(self, *a): self.load()
    def set_kind(self, v):
        self.kind = next((m for k, m in self.kinds.items() if T(k) == v), "image"); self.show()
    def load(self):
        if not self.app.rinfo:
            self.cnt.text = T("اتصل بجهاز العرض أولاً (وعلى نفس شبكة الواي فاي)"); return
        def run():
            try: st, d = self.app.rcall("GET", "/list"); items = d if isinstance(d, list) else []
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self.cnt, "text", T("تعذر الاتصال: %s" % e)), 0); return
            Clock.schedule_once(lambda dt: (setattr(self, "items", items), self.show()), 0)
        threading.Thread(target=run, daemon=True).start()
    def show(self):
        rows, total = mediaplan.filter_items(self.items, self.kind, self.q.text)
        self.cnt.text = T("%d ملف  |  المحدد: %d" % (total, len(self.sel)))
        self.lst.clear_widgets(); r = self.app.rinfo or {}
        for it in rows:
            row = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(3))
            cb = ToggleButton(text="✓", size_hint_x=.12, state="down" if it["uri"] in self.sel else "normal")
            cb.bind(state=lambda i, v, it=it: self.toggle(it, v == "down"))
            row.add_widget(cb)
            if self.kind != "audio" and r:
                row.add_widget(AsyncImage(source="http://%s:%d/thumb?t=%s&uri=%s" % (r["ip"], r["port"], r["token"], quote(it["uri"], safe="")), size_hint_x=.22))
            row.add_widget(L(it.get("name", "")[:30], halign="right"))
            row.add_widget(B("تشغيل", lambda it=it: self.play_one(it), GREEN, 44, 0.25))
            self.lst.add_widget(row)
    def toggle(self, it, on):
        if on: self.sel[it["uri"]] = it
        else: self.sel.pop(it["uri"], None)
        self.cnt.text = T("المحدد: %d" % len(self.sel))
    def play_one(self, it):
        sc = mediaplan.scene_for(it, self.repeat, self.cover)
        confirm("عرض «%s» على جهاز العرض؟" % it.get("name", ""), lambda: self.app.send("apply_scene", sc))
    def chosen(self): return [i for i in self.items if i["uri"] in self.sel]
    def play_selected(self):
        its = self.chosen()
        if not its: return self.app.toast("حدد ملفاً واحداً على الأقل")
        pl = mediaplan.playlist_payload(its, self.secs.text, self.repeat, self.cover)
        confirm("عرض %d ملف كقائمة تشغيل؟" % len(its), lambda: self.app.send("apply_playlist", pl))
    def save_selected(self):
        its = self.chosen()
        if not its: return self.app.toast("حدد ملفاً واحداً على الأقل")
        pl = mediaplan.playlist_payload(its, self.secs.text, self.repeat, self.cover)
        self.app.store.put("projects", {"name": "قائمة " + time.strftime("%m-%d %H:%M"), "scenes": pl["scenes"], "secs": pl["secs"]})
        self.app.toast("تم الحفظ في المشاريع (لم يُرسل)")
    def ctl(self, action, value=0): self.app.send("media", {"action": action, "value": value})
    def poll_state(self, dt):
        if self.app.sm.current == "rbrowser" and self.app.is_ready(): self.ctl("status")
    def show_state(self):
        st = self.app.media_state or {}
        if st.get("kind") in ("video", "audio"):
            self.state.text = T("%s | %s / %s | %s" % ("فيديو" if st["kind"] == "video" else "صوت", mediaplan.fmt_time(st.get("pos")),
                                                    mediaplan.fmt_time(st.get("dur")), "يعمل" if st.get("playing") else "متوقف مؤقتاً"))
        else: self.state.text = T("لا يوجد تشغيل")

class NewsStudio(Page):
    """V8 text & news studio: an independent main-text layer + an independent news ticker, live preview."""
    def __init__(self, app):
        super().__init__(app, "news", "استوديو النصوص والأخبار")
        self.tab = "main"; self._ev = None; self.ratio = 16 / 9
        self.new_scene()
        self.pvbox = FloatLayout(size_hint_y=None, height=dp(200))
        self.pv = FloatLayout(size_hint=(None, None))
        with self.pv.canvas.before:
            self.pc = Color(*H(self.bg)); self.pr = Rectangle()
        self.pv.bind(pos=lambda i, v: setattr(self.pr, "pos", v), size=lambda i, v: setattr(self.pr, "size", v))
        self.lv = LayersView(font=APP_FONT, fonts=BUNDLED, size_hint=(1, 1)); self.pv.add_widget(self.lv)
        self.pvbox.add_widget(self.pv); self.pvbox.bind(pos=self.fit, size=self.fit)
        self.body.add_widget(self.pvbox)
        tabs = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for key, name in (("main", "النص الرئيسي"), ("news", "شريط الأخبار"), ("scene", "المشهد")):
            tabs.add_widget(B(name, lambda k=key: self.show_tab(k), BLUE, 44))
        self.body.add_widget(tabs)
        self.panel = scroll_grid(self.body)
        r1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for name, cb, col in (("مشهد جديد", lambda: (self.new_scene(), self.refresh()), GREY), ("قوالب", lambda: app.go("tplv8"), GREY),
                              ("اتجاه المعاينة", self.flip, GREY), ("إعادة تشغيل", self.replay, GREY)):
            r1.add_widget(B(name, cb, col, 44))
        r2 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
        r2.add_widget(B("حفظ كمشهد", self.save_dialog, BLUE)); r2.add_widget(B("إرسال واعتماد وعرض", self.send_now, GREEN))
        self.body.add_widget(r1); self.body.add_widget(r2)
        Clock.schedule_once(lambda dt: self.refresh(), 0.3)

    # ---- scene state
    def new_scene(self):
        self.bg = "#0B1F3A"; self.extra = {}; self.tpl = ""
        self.layers = [S.normalize_layer({"id": "main", "kind": "text", "name": "النص الرئيسي", "x": .08, "y": .32, "w": .84, "h": .4,
                                          "text": "اكتب النص الرئيسي هنا", "size": .09, "anim_in": "fade"}),
                       S.normalize_layer({"id": "news", "kind": "ticker", "name": "شريط الأخبار", "x": 0, "y": .03, "w": 1, "h": .1,
                                          "items": ["الخبر الأول", "الخبر الثاني", "الخبر الثالث"], "bg": "#B71C1C", "size": .05})]

    def load_scene(self, scene):
        if isinstance(scene, dict) and scene.get("zones"):
            self.app.sm.get_screen("zones").load_scene(scene); return self.app.go("zones")
        sc = S.normalize_scene(scene)
        self.bg = sc.get("bg", "#0B1F3A"); self.tpl = sc.get("tpl", "")
        self.layers = sc.get("layers", [])
        self.extra = {k: v for k, v in sc.items() if k not in ("layers", "bg", "tpl")}
        for lid, kind, extra in (("main", "text", {"text": "", "hidden": True}), ("news", "ticker", {"hidden": True})):
            if not S.find(self.layers, lid): S.add_layer(self.layers, dict(extra, id=lid, kind=kind, name=lid))
        self.panel.clear_widgets(); self.build_panel(); self.refresh()

    def payload(self):
        self.layers[:] = S.normalize_scene({"layers": self.layers})["layers"]
        sc = dict(self.extra); sc["bg"] = self.bg; sc["layers"] = copy.deepcopy(self.layers)
        if self.tpl: sc["tpl"] = self.tpl
        return sc

    def get(self, lid, key): return S.find(self.layers, lid).get(key)
    def set(self, lid, key, val):
        l = S.find(self.layers, lid)
        if l is not None: l[key] = val; self.touch()

    # ---- preview
    def on_pre_enter(self, *a): self.build_panel(); self.refresh()
    def fit(self, *a):
        W, Hh = self.pvbox.size; w = min(W, Hh * self.ratio); h = w / self.ratio
        self.pv.size = (w, h); self.pv.pos = (self.pvbox.x + (W - w) / 2, self.pvbox.y + (Hh - h) / 2)
    def flip(self): self.ratio = 9 / 16 if self.ratio > 1 else 16 / 9; self.fit(); self.touch()
    def touch(self):
        if self._ev: self._ev.cancel()
        self._ev = Clock.schedule_once(lambda dt: self.refresh(), 0.35)
    def refresh(self):
        self.fit(); self.pc.rgba = H(self.bg)
        self.lv.set_layers(S.normalize_scene({"layers": self.layers})["layers"])
    def replay(self):
        for lid in list(self.lv.rt): self.lv.control(lid, "restart")

    # ---- panel builders
    def show_tab(self, k): self.tab = k; self.build_panel()
    def _row(self, label, widget, h=44):
        row = BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(4))
        row.add_widget(L(label, size_hint_x=.32, halign="right")); row.add_widget(widget); self.panel.add_widget(row)
    def slider(self, lid, key, label, lo, hi):
        sl = Slider(min=lo, max=hi, value=float(self.get(lid, key) or 0))
        sl.bind(value=lambda i, v: self.set(lid, key, v)); self._row(label, sl)
    def choice(self, lid, key, label, mapping):
        cur = self.get(lid, key); name = next((k for k, v in mapping.items() if v == cur), next(iter(mapping)))
        sp = SP(T(name), [T(k) for k in mapping])
        sp.bind(text=lambda i, v: self.set(lid, key, next((m for k, m in mapping.items() if T(k) == v), cur)))
        self._row(label, sp)
    def color(self, lid, key, label):
        cur = self.get(lid, key) or "#000000"
        b = Button(background_normal="", background_color=H(cur))
        def done(v): self.set(lid, key, v); b.background_color = H(v)
        b.bind(on_release=lambda *_: pick_color(label, self.get(lid, key) or "#000000", done)); self._row(label, b)
    def entry(self, lid, key, label, as_lines=False):
        v = self.get(lid, key); ti = TI("\n".join(v) if as_lines else v, ml=True, h=110)
        ti.bind(text=lambda i, t: self.set(lid, key, t.splitlines() if as_lines else t)); self._row(label, ti, 110)
    def geometry(self, lid):
        for key, label, lo, hi in (("x", "الموضع أفقياً", 0, 1), ("y", "الموضع عمودياً", 0, 1), ("w", "العرض", .1, 1),
                                   ("h", "الارتفاع", .04, 1), ("opacity", "الشفافية", 0, 1), ("rotation", "التدوير", -180, 180)):
            self.slider(lid, key, label, lo, hi)
    def style(self, lid):
        self.slider(lid, "size", "حجم الخط", .02, .3); self.color(lid, "color", "لون النص"); self.choice(lid, "font", "نوع الخط", V8_FONT)
        self.color(lid, "bg", "لون الخلفية"); self.slider(lid, "bg_opacity", "شفافية الخلفية", 0, 1); self.choice(lid, "align", "المحاذاة", V8_ALIGN)
    def anims(self, lid):
        self.choice(lid, "anim_in", "تأثير الظهور", V8_IN); self.slider(lid, "dur", "مدة التأثير (ث)", .1, 5)
        self.choice(lid, "anim_out", "تأثير الاختفاء", V8_OUT); self.slider(lid, "hold", "الاختفاء بعد (ث، 0=لا)", 0, 120)
    def cmd_row(self, lid, pairs):
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for name, act in pairs: row.add_widget(B(name, lambda a=act: self.live(lid, a), GREY, 44))
        self.panel.add_widget(row)
    def live(self, lid, action):                      # applies to the preview and, if connected, to the Receiver
        self.lv.control(lid, action)
        if self.app.is_ready(): self.app.send("layer", {"id": lid, "action": action})
        else: self.app.toast("تم على المعاينة فقط (غير متصل)")

    def build_panel(self):
        self.panel.clear_widgets()
        if self.tab == "main":
            self.cmd_row("main", (("إخفاء", "hide"), ("إظهار", "show"), ("إعادة الحركة", "restart")))
            self.entry("main", "text", "النص"); self.style("main"); self.anims("main"); self.geometry("main")
        elif self.tab == "news":
            self.cmd_row("news", (("إيقاف الحركة", "pause"), ("استئناف", "resume"), ("إخفاء", "hide"), ("إظهار", "show")))
            self.entry("news", "items", "الأخبار (سطر لكل خبر)", as_lines=True)
            self.choice("news", "mode", "نمط العرض", V8_MODE); self.choice("news", "dir", "اتجاه الحركة", V8_DIR)
            self.slider("news", "speed", "السرعة", 1, 10); self.slider("news", "seq_hold", "مدة كل خبر (متتابع)", 1, 30)
            sep = SP(T("✦"), list(V8_SEP)); sep.bind(text=lambda i, v: self.set("news", "sep", V8_SEP.get(v, "  ✦  "))); self._row("الفاصل بين الأخبار", sep)
            self.style("news"); self.choice("news", "anim_in", "تأثير الظهور", V8_IN); self.geometry("news")
        else:
            bgb = Button(background_normal="", background_color=H(self.bg))
            def done(v): self.bg = v; bgb.background_color = H(v); self.touch()
            bgb.bind(on_release=lambda *_: pick_color("خلفية المشهد", self.bg, done)); self._row("خلفية المشهد", bgb)
            others = [l for l in self.layers if l["id"] not in ("main", "news")]
            self.panel.add_widget(L("طبقات إضافية من القالب: %d%s" % (len(others), "  (" + "، ".join((l.get("name") or l["id"]) for l in others[:6]) + ")" if others else ""), 60))
            self.panel.add_widget(L("لتعديل نصوص القالب الإضافية افتح القالب من «قوالب» وغيّر الحقول.", 40))

    # ---- actions
    def send_now(self):
        sc = self.payload()
        self.app.send_scene(sc)
    def save_dialog(self):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6)); ti = TI("مشهد " + time.strftime("%H:%M")); box.add_widget(ti)
        p = popup("اسم المشهد", box, (0.9, 0.4)); row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        def save():
            p.dismiss(); self.app.store.put("scenes", {"name": ti.text.strip() or "مشهد", "scene": self.payload()}); self.app.toast("تم حفظ المشهد")
        row.add_widget(B("إلغاء", p.dismiss, GREY)); row.add_widget(B("حفظ", save, GREEN)); box.add_widget(row)

class TemplatesV8(Page):
    """Ready-made, editable templates: pick one, fill the fields, open it in the studio."""
    def __init__(self, app):
        super().__init__(app, "tplv8", "قوالب الأخبار والإعلانات")
        g = scroll_grid(self.body)
        for t in S.TEMPLATES: g.add_widget(B(t["name"], lambda t=t: self.edit(t), BLUE, 56))
    def edit(self, t):
        d = t["defaults"]; box = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(6)); ins = {}
        for key, label, ml in (("title", "العنوان", False), ("main", "النص الرئيسي", False), ("sub", "نص إضافي", False), ("ticker", "الأخبار (سطر لكل خبر)", True)):
            box.add_widget(L(label, 22)); v = d.get(key, ""); ins[key] = TI("\n".join(v) if isinstance(v, list) else v, ml=ml, h=90 if ml else 44); box.add_widget(ins[key])
        p = popup(t["name"], box, (0.94, 0.9)); row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        def build(): return S.build_template(t["id"], {k: w.text for k, w in ins.items()})
        def open_():
            p.dismiss(); st = self.app.sm.get_screen("news"); st.load_scene(build()); self.app.go("news")
        row.add_widget(B("إلغاء", p.dismiss, GREY)); row.add_widget(B("فتح في الاستوديو", open_, BLUE))
        row.add_widget(B("إرسال", lambda: (p.dismiss(), self.app.send_scene(build())), GREEN)); box.add_widget(row)

class Soon(Page):
    def __init__(self, app, key, title, why):
        super().__init__(app, key, title)
        self.body.add_widget(L(why))

# ---------- Workspace: live preview + a customizable bar of named cells ----------
FIT_MODES = {"احتواء": "contain", "تغطية": "cover", "تمديد": "fill", "تصغير فقط": "scale-down"}

class DragFloat(FloatLayout):
    """Preview surface. While `on_drag` is set, touching/dragging inside it reports the finger as (fx, fy) fractions."""
    on_drag = None
    on_drop = None
    def _frac(self, t): return (t.x - self.x) / max(self.width, 1), (t.y - self.y) / max(self.height, 1)
    def on_touch_down(self, t):
        if self.on_drag and self.collide_point(*t.pos):
            t.grab(self); self.on_drag(*self._frac(t)); return True
        return super().on_touch_down(t)
    def on_touch_move(self, t):
        if t.grab_current is self: self.on_drag(*self._frac(t)); return True
        return super().on_touch_move(t)
    def on_touch_up(self, t):
        if t.grab_current is self:
            t.ungrab(self)
            if self.on_drop: self.on_drop()
            return True
        return super().on_touch_up(t)

class Workspace(Screen):
    """Main screen. Top: live preview. Bottom: N cells (4..10). A cell opens a settings panel, runs an action,
    or opens one of the older screens. Cells can hold a whole group or a single setting (see workspace_model)."""
    def __init__(self, app):
        super().__init__(name="home")
        self.app = app; self._ev = None; self.ratio = 16 / 9; self.open_i = None; self.sel = None; self.sel_img = None; self.drag_target = None; self._vol = None
        self.screens = dict(app.page_titles)
        self.cfg = WM.normalize(app.store.d["settings"].get("ws"), self.screens)
        self.new_scene()
        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(4)); self.add_widget(root)
        top = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        top.add_widget(B("تخصيص", self.customize, GREY, 44, 0.24)); top.add_widget(app.status)
        top.add_widget(B("إرسال واعتماد وعرض", self.send_now, GREEN, 44, 0.46)); root.add_widget(top)
        self.pvbox = FloatLayout()
        self.pv = DragFloat(size_hint=(None, None)); self.pv.on_drop = self.drop
        with self.pv.canvas.before:
            self.pc = Color(*H(self.bg)); self.pr = Rectangle()
        self.pv.bind(pos=lambda i, v: setattr(self.pr, "pos", v), size=lambda i, v: setattr(self.pr, "size", v))
        self.pimg = Image(size_hint=(1, 1), allow_stretch=True, keep_ratio=True, opacity=0)
        self.pnote = L("", 30, font_size="13sp", pos_hint={"x": 0, "y": 0})
        self.lv = LayersView(font=APP_FONT, fonts=BUNDLED, resolver=lambda d: self.app.thumb_path(d.get("path")) if d.get("path") else None, size_hint=(1, 1))
        for w in (self.pimg, self.lv, self.pnote): self.pv.add_widget(w)
        self.pvbox.add_widget(self.pv); self.pvbox.bind(pos=self.fit, size=self.fit); root.add_widget(self.pvbox)
        # settings panel (closed = zero height)
        self.panel = BoxLayout(orientation="vertical", size_hint_y=None, height=0, opacity=0, padding=dp(4), spacing=dp(3))
        with self.panel.canvas.before:
            Color(0.05, 0.08, 0.14, 0.97); self.panel_r = Rectangle()
        self.panel.bind(pos=lambda i, v: setattr(self.panel_r, "pos", v), size=lambda i, v: setattr(self.panel_r, "size", v))
        hdr = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        hdr.add_widget(B("إغلاق", self.close_panel, GREY, 38, 0.28)); self.ptitle = L("", 38, font_size="17sp"); hdr.add_widget(self.ptitle)
        self.panel.add_widget(hdr)
        sv = ScrollView(); self.pg = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
        self.pg.bind(minimum_height=self.pg.setter("height")); sv.add_widget(self.pg); self.panel.add_widget(sv)
        root.add_widget(self.panel)
        self.bar = GridLayout(cols=3, size_hint_y=None, spacing=dp(4)); root.add_widget(self.bar)
        self.build_bar()
        Clock.schedule_once(lambda dt: self.refresh(), 0.3)

    # ---- scene state
    def new_scene(self):
        self.bg = "#0B1F3A"; self.visual = None; self.audio = None; self.sel = None; self.sel_img = None
        self.layers = [S.normalize_layer({"id": "main", "kind": "text", "name": "النص الرئيسي", "x": .08, "y": .32, "w": .84,
                                          "h": .4, "text": "اكتب النص هنا", "size": .09, "anim_in": "fade"})]
    def load_scene(self, scene):
        if isinstance(scene, dict) and scene.get("zones"):                 # a split-screen layout opens in its own studio
            self.app.sm.get_screen("zones").load_scene(scene); return self.app.go("zones")
        sc = S.normalize_scene(scene)
        self.bg = sc.get("bg", "#0B1F3A"); self.layers = sc.get("layers", [])
        if not S.find(self.layers, "main"): S.add_layer(self.layers, {"id": "main", "kind": "text", "name": "النص الرئيسي", "text": "", "hidden": True})
        self.visual = sc.get("visual") or None; self.audio = sc.get("audio") or None
        self.sel = next((l["id"] for l in self.extras()), None); self.sel_img = next((l["id"] for l in self.imgs()), None)
        self.refresh(); self.reopen()
    def payload(self):
        self.layers[:] = S.normalize_scene({"layers": self.layers})["layers"]
        sc = {"bg": self.bg, "layers": copy.deepcopy(self.layers)}
        if self.visual: sc["visual"] = dict(self.visual)
        if self.audio: sc["audio"] = dict(self.audio)
        return sc
    def get(self, lid, key):
        l = S.find(self.layers, lid); return l.get(key) if l else None
    def set(self, lid, key, val):
        l = S.find(self.layers, lid)
        if l is not None: l[key] = val; self.touch()
    def extras(self): return [l for l in self.layers if l["kind"] == "text" and l["id"] not in ("main", "news")]
    def imgs(self): return [l for l in self.layers if l["kind"] == "image"]

    # ---- preview
    def on_pre_enter(self, *a): self.refresh()
    def fit(self, *a):
        W, Hh = self.pvbox.size
        if W <= 0 or Hh <= 0: return
        w = min(W, Hh * self.ratio); h = w / self.ratio
        self.pv.size = (w, h); self.pv.pos = (self.pvbox.x + (W - w) / 2, self.pvbox.y + (Hh - h) / 2)
    def touch(self):
        if self._ev: self._ev.cancel()
        self._ev = Clock.schedule_once(lambda dt: self.refresh(), 0.35)
    def refresh(self):
        self.fit(); self.pc.rgba = H(self.bg)
        v = self.visual; note = ""
        if v and v.get("kind") == "image" and v.get("src") == "local" and v.get("path") and os.path.isfile(v["path"]):
            self.pimg.source = self.app.thumb_path(v["path"]); self.pimg.opacity = 1
            try: self.pimg.fit_mode = v.get("fit") if v.get("fit") in FIT_MODES.values() else "contain"
            except Exception: pass
        else:
            self.pimg.source = ""; self.pimg.opacity = 0
            if v: note = "%s: %s" % (KINDS.get(v.get("kind"), ""), str(v.get("name", ""))[:24])
        if self.audio: note = (note + "  |  " if note else "") + "صوت: " + str(self.audio.get("name", ""))[:24]
        self.pnote.text = T(note)
        self.lv.set_layers(S.normalize_scene({"layers": self.layers})["layers"])

    # ---- bottom bar
    def build_bar(self):
        self.bar.clear_widgets()
        cells = WM.visible(self.cfg); cols, rows = WM.layout(len(cells))
        self.bar.cols = cols; self.bar.height = dp(54) * rows + dp(4) * (rows - 1)
        order = []                                   # right-to-left: cell 1 sits at the right edge
        for r in range(rows):
            chunk = list(range(r * cols, min(len(cells), (r + 1) * cols)))
            order += [None] * (cols - len(chunk)) + chunk[::-1]
        for i in order:
            if i is None: self.bar.add_widget(Widget()); continue
            c = cells[i]; kind = c["type"].split(":", 1)[0]
            col = "#0D47A1" if i == self.open_i else (BLUE if kind in ("group", "setting") else (RED if c["type"] == "action:clear" else (GREEN if c["type"] == "action:send" else GREY)))
            btn = B(c["name"], lambda i=i: self.tap(i), col, 54)
            btn.font_size = "13sp"; btn.halign = "center"; btn.valign = "middle"
            btn.bind(size=lambda inst, v: setattr(inst, "text_size", (v[0] - dp(6), v[1])))
            self.bar.add_widget(btn)
    def tap(self, i):
        c = WM.visible(self.cfg)[i]; t = c["type"]; kind, key = t.split(":", 1)
        if kind in ("group", "setting"):
            if self.open_i == i: return self.close_panel()
            self.open_panel(i)
        elif kind == "action": self.close_panel(); self.run_action(key)
        elif kind == "screen": self.close_panel(); self.app.go(key)
    def persist(self):
        self.app.store.d["settings"]["ws"] = copy.deepcopy(self.cfg); self.app.store.save()

    # ---- panel
    def open_panel(self, i):
        self.open_i = i; c = WM.visible(self.cfg)[i]; items = WM.panel_items(c["type"])
        self.ptitle.text = T(c["name"]); self.pg.clear_widgets(); self.drag_target = None
        for k in items:
            if len(items) > 1: self.pg.add_widget(L(WM.SETTINGS[k], 26, color=(0.6, 0.8, 1, 1), font_size="14sp"))
            fn = getattr(self, "s_" + k.replace(".", "_"), None)
            try:
                if fn is None: raise ValueError("no builder " + k)
                fn(self.pg)
            except Exception as e:
                self.pg.add_widget(L("تعذر عرض هذا الإعداد: %s" % e, 40))
        self.pv.on_drag = self.drag_to if self.drag_target else None
        self.panel.height = max(dp(220), min(dp(400), Window.height * 0.46)); self.panel.opacity = 1
        self.build_bar(); Clock.schedule_once(lambda dt: self.fit(), 0.05)
    def reopen(self):
        if self.open_i is not None and self.open_i < len(WM.visible(self.cfg)): self.open_panel(self.open_i)
    def close_panel(self):
        self.open_i = None; self.drag_target = None; self.pv.on_drag = None
        self.panel.height = 0; self.panel.opacity = 0; self.pg.clear_widgets(); self.build_bar()
        Clock.schedule_once(lambda dt: self.fit(), 0.05)

    # ---- drag a layer inside the preview
    def drag_to(self, fx, fy):
        lid = self.drag_target; l = S.find(self.layers, lid) if lid else None
        if l is None: return
        l["x"] = max(-0.5, min(1.0, fx - l["w"] / 2)); l["y"] = max(-0.5, min(1.0, fy - l["h"] / 2))
        rt = self.lv.rt.get(lid)                      # move the live box directly: no rebuild, no animation restart
        if rt is not None:
            rt.d["x"], rt.d["y"] = l["x"], l["y"]; rt.box.pos_hint = {"x": l["x"], "y": l["y"]}
    def drop(self): self.reopen()                     # refresh the sliders to the new position
    def _drag_note(self, box, lid):
        if lid and S.find(self.layers, lid):
            self.drag_target = lid; box.add_widget(L("اسحب بإصبعك داخل المعاينة لتحريك العنصر", 30, font_size="13sp"))

    # ---- setting widgets (all take the container; text.* edit the main layer, extra.* the selected extra layer)
    def _row(self, box, label, widget, h=44):
        row = BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(4))
        row.add_widget(L(label, size_hint_x=.32, halign="right")); row.add_widget(widget); box.add_widget(row)
    def _slider(self, box, lid, key, label, lo, hi):
        sl = Slider(min=lo, max=hi, value=float(self.get(lid, key) or 0))
        sl.bind(value=lambda i, v: self.set(lid, key, v)); self._row(box, label, sl)
    def _choice(self, box, lid, key, label, mapping):
        cur = self.get(lid, key); name = next((k for k, v in mapping.items() if v == cur), next(iter(mapping)))
        sp = SP(T(name), [T(k) for k in mapping])
        sp.bind(text=lambda i, v: self.set(lid, key, next((m for k, m in mapping.items() if T(k) == v), cur)))
        self._row(box, label, sp)
    def _color(self, box, lid, key, label):
        cur = self.get(lid, key) or "#000000"; b = Button(background_normal="", background_color=H(cur))
        def done(v): self.set(lid, key, v); b.background_color = H(v)
        b.bind(on_release=lambda *_: pick_color(label, self.get(lid, key) or "#000000", done)); self._row(box, label, b)
    def _entry(self, box, lid, key, label):
        ti = TI(self.get(lid, key) or "", ml=True, h=110); ti.bind(text=lambda i, t: self.set(lid, key, t)); self._row(box, label, ti, 110)
    def _need(self, box, lid):
        if lid and S.find(self.layers, lid): return True
        box.add_widget(L("أضف نصاً إضافياً أولاً من خانة «نص إضافي»", 40)); return False
    def _text_entry(self, box, lid): 
        if self._need(box, lid): self._entry(box, lid, "text", "النص")
    def _text_color(self, box, lid):
        if self._need(box, lid): self._color(box, lid, "color", "لون النص")
    def _text_size(self, box, lid):
        if self._need(box, lid): self._slider(box, lid, "size", "حجم النص", .02, .3)
    def _text_pos(self, box, lid):
        if self._need(box, lid):
            self._drag_note(box, lid)
            for key, label, lo, hi in (("x", "الموضع أفقياً", 0, 1), ("y", "الموضع عمودياً", 0, 1), ("w", "العرض", .1, 1), ("h", "الارتفاع", .04, 1),
                                       ("opacity", "الشفافية", 0, 1), ("rotation", "التدوير", -180, 180)):
                self._slider(box, lid, key, label, lo, hi)
    def live(self, lid, action):
        self.lv.control(lid, action)
        if self.app.is_ready(): self.app.send("layer", {"id": lid, "action": action})
        else: self.app.toast("تم على المعاينة فقط (غير متصل)")

    # text group
    def s_text_entry(self, box): self._text_entry(box, "main")
    def s_text_color(self, box): self._text_color(box, "main")
    def s_text_bg(self, box): self._color(box, "main", "bg", "لون الخلفية"); self._slider(box, "main", "bg_opacity", "شفافية الخلفية", 0, 1)
    def s_text_size(self, box): self._text_size(box, "main")
    def s_text_align(self, box): self._choice(box, "main", "align", "المحاذاة", V8_ALIGN)
    def s_text_font(self, box): self._choice(box, "main", "font", "نوع الخط", V8_FONT)
    def s_text_anim(self, box):
        self._choice(box, "main", "anim_in", "تأثير الظهور", V8_IN); self._slider(box, "main", "dur", "مدة التأثير (ث)", .1, 5)
        self._choice(box, "main", "anim_out", "تأثير الاختفاء", V8_OUT); self._slider(box, "main", "hold", "الاختفاء بعد (ث، 0=لا)", 0, 120)
    def s_text_pos(self, box): self._text_pos(box, "main")
    def s_text_live(self, box):
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for name, act in (("إخفاء", "hide"), ("إظهار", "show"), ("إعادة الحركة", "restart")):
            row.add_widget(B(name, lambda a=act: self.live("main", a), GREY, 44))
        box.add_widget(row)

    # extra text group
    def s_extra_manage(self, box):
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        row.add_widget(B("+ نص جديد", self.add_extra, GREEN, 44)); row.add_widget(B("حذف المحدد", self.del_extra, RED, 44)); box.add_widget(row)
        ex = self.extras()
        if not ex: return box.add_widget(L("لا توجد نصوص إضافية", 36))
        names = {"نص %d" % (n + 1): l["id"] for n, l in enumerate(ex)}
        cur = next((k for k, v in names.items() if v == self.sel), None) or next(iter(names)); self.sel = names[cur]
        sp = SP(T(cur), [T(k) for k in names])
        def chosen(i, v):
            self.sel = next((lid for k, lid in names.items() if T(k) == v), self.sel); self.reopen()
        sp.bind(text=chosen); self._row(box, "المحدد", sp)
    def add_extra(self):
        n = len(self.extras()) + 1
        l = S.add_layer(self.layers, {"kind": "text", "name": "نص %d" % n, "text": "نص إضافي %d" % n, "x": .1, "y": max(.05, .78 - .12 * n),
                                      "w": .8, "h": .12, "size": .06, "anim_in": "fade"})
        self.sel = l["id"]; self.refresh(); self.reopen()
    def del_extra(self):
        if self.sel and S.remove_layer(self.layers, self.sel): self.sel = None; self.refresh(); self.reopen()
    def s_extra_entry(self, box): self._text_entry(box, self.sel)
    def s_extra_color(self, box): self._text_color(box, self.sel)
    def s_extra_size(self, box): self._text_size(box, self.sel)
    def s_extra_pos(self, box): self._text_pos(box, self.sel)

    # media group
    def set_visual(self, item):
        self.visual = dict(item, loop=True, fit="contain") if item else None; self.refresh()
        self.app.toast("تم اختيار: %s" % item["name"] if item else "تمت إزالة الصورة/الفيديو")
    def set_audio(self, item):
        self.audio = dict(item, loop=True) if item else None; self.refresh(); self.app.toast("تم اختيار الصوت: %s" % item["name"])
    def media_cmd(self, action, value=0):
        self.app.send("media", {"action": action, "value": value})
    def s_media_video(self, box): box.add_widget(B("اختيار فيديو", lambda: self.app.choose_media("video", self.set_visual), BLUE))
    def s_media_audio(self, box): box.add_widget(B("اختيار صوت", lambda: self.app.choose_media("audio", self.set_audio), BLUE))
    def s_media_control(self, box):
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
        for name, cb in (("تشغيل الآن", self.send_now), ("استئناف", lambda: self.media_cmd("resume")), ("إيقاف مؤقت", lambda: self.media_cmd("pause")),
                         ("من البداية", lambda: self.media_cmd("seek", 0))):
            row.add_widget(B(name, cb, GREEN if name == "تشغيل الآن" else GREY, 48))
        box.add_widget(row)
    def s_media_volume(self, box):
        sl = Slider(min=0, max=100, value=70, step=5)
        def ch(i, v):
            if self._vol: self._vol.cancel()
            self._vol = Clock.schedule_once(lambda dt: self.media_cmd("volume", int(v)), 0.5)
        sl.bind(value=ch); self._row(box, "مستوى الصوت", sl)
    def s_media_loop(self, box):
        m = self.visual or self.audio
        tb = ToggleButton(text=T("تكرار الفيديو والصوت"), state="down" if (m.get("loop", True) if m else True) else "normal",
                          size_hint_y=None, height=dp(44), **F)
        def ch(i, st):
            for x in (self.visual, self.audio):
                if x: x["loop"] = (st == "down")
        tb.bind(state=ch); box.add_widget(tb)
    def s_media_sender_list(self, box):
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
        row.add_widget(B("فيديوهات الجوال", lambda: self.app.library_chooser("video", self.set_visual), BLUE, 48))
        row.add_widget(B("أصوات الجوال", lambda: self.app.library_chooser("audio", self.set_audio), BLUE, 48)); box.add_widget(row)
    def s_media_receiver_list(self, box):
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
        row.add_widget(B("فيديوهات جهاز العرض", lambda: self.app.remote_gallery("video", self.set_visual), BLUE, 48))
        row.add_widget(B("أصوات جهاز العرض", lambda: self.app.remote_gallery("audio", self.set_audio), BLUE, 48)); box.add_widget(row)

    # image group (images are layers: any place, any size, own entrance effect)
    def add_image(self, item):
        if not item or item.get("kind") != "image": return
        n = len(self.imgs()) + 1
        l = S.add_layer(self.layers, {"kind": "image", "name": "صورة %d" % n, "src": item.get("src", "local"), "file": item.get("name", ""),
                                      "path": item.get("path", ""), "uri": item.get("uri", ""), "fit": "contain", "anim_in": "fade"})
        if not S.find(self.layers, l["id"]): return self.app.toast("وصلت إلى الحد الأقصى للطبقات")
        self.sel_img = l["id"]; self.refresh(); self.reopen(); self.app.toast("تم إدراج الصورة: %s" % item.get("name", ""))
    def _img(self, box):
        """Selected image layer id, or None (with a hint shown)."""
        if self.sel_img and S.find(self.layers, self.sel_img): return self.sel_img
        self.sel_img = next((l["id"] for l in self.imgs()), None)
        if self.sel_img: return self.sel_img
        box.add_widget(L("أدرج صورة أولاً من «إدراج صورة»", 40)); return None
    def s_image_pick(self, box): box.add_widget(B("إدراج صورة", lambda: self.app.choose_media("image", self.add_image), BLUE))
    def s_image_manage(self, box):
        ims = self.imgs()
        if not ims: return box.add_widget(L("لا توجد صور مدرجة", 36))
        names = {"صورة %d" % (n + 1): l["id"] for n, l in enumerate(ims)}
        cur = next((k for k, v in names.items() if v == self.sel_img), None) or next(iter(names)); self.sel_img = names[cur]
        sp = SP(T(cur), [T(k) for k in names])
        def chosen(i, v):
            self.sel_img = next((lid for k, lid in names.items() if T(k) == v), self.sel_img); self.reopen()
        sp.bind(text=chosen); self._row(box, "المحددة", sp)
    def s_image_size(self, box):
        lid = self._img(box)
        if not lid: return
        w0, h0 = self.get(lid, "w") or .5, self.get(lid, "h") or .5
        sw = Slider(min=.05, max=1, value=float(w0)); sh = Slider(min=.05, max=1, value=float(h0)); su = Slider(min=.2, max=2.5, value=1.0)
        sw.bind(value=lambda i, v: self.set(lid, "w", v)); sh.bind(value=lambda i, v: self.set(lid, "h", v))
        def scale(i, f):
            sw.value = max(.05, min(1.0, w0 * f)); sh.value = max(.05, min(1.0, h0 * f))     # moves both sliders -> both sizes
        su.bind(value=scale)
        self._row(box, "الحجم (تكبير/تصغير)", su); self._row(box, "العرض", sw); self._row(box, "الارتفاع", sh)
    def s_image_pos(self, box):
        lid = self._img(box)
        if not lid: return
        self._drag_note(box, lid)
        self._slider(box, lid, "x", "الموضع أفقياً", -.5, 1); self._slider(box, lid, "y", "الموضع عمودياً", -.5, 1)
        def put(fx, fy):                               # fx, fy = where the image CENTER should be (0..1)
            self.set(lid, "x", fx - (self.get(lid, "w") or .5) / 2); self.set(lid, "y", fy - (self.get(lid, "h") or .5) / 2)
            self.refresh(); self.reopen()
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for name, fx, fy in (("أعلى يمين", .8, .8), ("أعلى يسار", .2, .8), ("وسط", .5, .5), ("أسفل يمين", .8, .2), ("أسفل يسار", .2, .2)):
            row.add_widget(B(name, lambda fx=fx, fy=fy: put(fx, fy), GREY, 44))
        box.add_widget(row)
    def s_image_anim(self, box):
        lid = self._img(box)
        if not lid: return
        self._choice(box, lid, "anim_in", "كيف تظهر", IMG_IN); self._slider(box, lid, "dur", "مدة الظهور (ث)", .1, 5)
        self._choice(box, lid, "anim_out", "كيف تختفي", V8_OUT); self._slider(box, lid, "hold", "تختفي بعد (ث، 0 = تبقى)", 0, 120)
        box.add_widget(B("معاينة الحركة", lambda: self.lv.control(lid, "restart"), GREY, 40))
    def s_image_fit(self, box):
        lid = self._img(box)
        if lid: self._choice(box, lid, "fit", "طريقة العرض", FIT_MODES)
    def s_image_style(self, box):
        lid = self._img(box)
        if lid: self._slider(box, lid, "opacity", "الشفافية", 0, 1); self._slider(box, lid, "rotation", "التدوير", -180, 180)
    def s_image_live(self, box):
        lid = self._img(box)
        if not lid: return
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for name, act in (("إخفاء", "hide"), ("إظهار", "show"), ("إعادة الحركة", "restart")):
            row.add_widget(B(name, lambda a=act: self.live(lid, a), GREY, 44))
        box.add_widget(row)
    def del_image(self):
        if self.sel_img and S.remove_layer(self.layers, self.sel_img): self.sel_img = None; self.refresh(); self.reopen()
        elif self.visual and self.visual.get("kind") == "image": self.set_visual(None)
    def s_image_remove(self, box): box.add_widget(B("حذف الصورة المحددة", self.del_image, RED))

    # project group
    def s_project_open(self, box):
        box.add_widget(B("اختيار مشهد محفوظ", self.pick_scene, BLUE))
    def pick_scene(self):
        b = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6)); p = popup("المشاهد المحفوظة", b, (0.94, 0.8)); g = scroll_grid(b)
        items = self.app.store.items("scenes", "")
        if not items: g.add_widget(L("لا توجد مشاهد محفوظة بعد", 40))
        for it in items:
            g.add_widget(B(it.get("name", "مشهد")[:34], lambda it=it: (p.dismiss(), self.load_scene(it["scene"])), BLUE, 48))
        b.add_widget(B("إغلاق", p.dismiss, GREY))
    def s_project_save(self, box): box.add_widget(B("حفظ المشهد الحالي", self.save_dialog, GREEN))
    def s_project_new(self, box): box.add_widget(B("مشهد جديد", lambda: confirm("بدء مشهد جديد؟ ستفقد التعديلات غير المحفوظة.", lambda: (self.new_scene(), self.refresh(), self.reopen())), GREY))
    def s_project_templates(self, box): box.add_widget(B("القوالب الجاهزة", lambda: self.app.go("tplv8"), GREY))
    def s_project_projects(self, box): box.add_widget(B("المشاريع", lambda: self.app.go("projects"), GREY))
    def save_dialog(self):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6)); ti = TI("مشهد " + time.strftime("%H:%M")); box.add_widget(ti)
        p = popup("اسم المشهد", box, (0.9, 0.4)); row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        def save():
            p.dismiss(); self.app.store.put("scenes", {"name": ti.text.strip() or "مشهد", "scene": self.payload()}); self.app.toast("تم حفظ المشهد")
        row.add_widget(B("إلغاء", p.dismiss, GREY)); row.add_widget(B("حفظ", save, GREEN)); box.add_widget(row)

    # more group
    def s_more_content(self, box): box.add_widget(B("فتح مدير المحتوى المتقدم", lambda: self.app.go("content"), BLUE))
    def s_more_texts(self, box): box.add_widget(B("فتح إدارة النصوص", lambda: self.app.go("text_manager"), BLUE))
    def s_more_design(self, box): box.add_widget(B("فتح استديو التصميم", lambda: self.app.go("design_hub"), BLUE))
    def s_more_emergency(self, box): box.add_widget(B("فتح وضع الطوارئ", lambda: self.app.go("emergency"), RED))
    def s_more_split(self, box):
        box.add_widget(B("تقسيم الشاشة (محتوى مستقل لكل منطقة)", lambda: self.app.go("zones"), GREEN))
    def s_more_customize(self, box): box.add_widget(B("تخصيص الخانات (العدد والأسماء والمحتوى)", self.customize, BLUE))
    def s_more_all(self, box): box.add_widget(B("كل الميزات (القائمة الكاملة)", lambda: self.app.go("all"), GREY))

    # ---- actions
    def send_now(self): self.app.send_scene(self.payload())
    def run_action(self, key):
        a = self.app
        if key == "send": self.send_now()
        elif key == "hide": a.send("hide", {})
        elif key == "restore": a.send("restore", {})
        elif key == "clear": confirm("مسح الشاشة؟", lambda: a.send("clear", {}))
        elif key == "media_pause": self.media_cmd("pause")
        elif key == "media_resume": self.media_cmd("resume")
        elif key == "media_restart": self.media_cmd("seek", 0)
        elif key == "replay":
            for lid in list(self.lv.rt): self.lv.control(lid, "restart")

    # ---- customize cells
    def customize(self):
        self.close_panel()
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6)); p = popup("تخصيص الخانات", box, (0.97, 0.92))
        cnt = L("", 36); row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        row.add_widget(B("−", lambda: count(-1), GREY, 44, 0.2)); row.add_widget(cnt); row.add_widget(B("+", lambda: count(1), GREY, 44, 0.2))
        box.add_widget(row)
        lst = scroll_grid(box)
        def redraw():
            cnt.text = T("عدد الخانات: %d" % self.cfg["n"]); lst.clear_widgets()
            for i, c in enumerate(WM.visible(self.cfg)):
                r = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
                r.add_widget(B("▲", lambda i=i: change(lambda: WM.move_cell(self.cfg, i, -1)), GREY, 44, 0.12))
                r.add_widget(B("▼", lambda i=i: change(lambda: WM.move_cell(self.cfg, i, 1)), GREY, 44, 0.12))
                ti = TI(c["name"], h=44); ti.bind(text=lambda inst, t, i=i: (WM.rename_cell(self.cfg, i, t), self.persist()))
                r.add_widget(ti)
                r.add_widget(B(WM.type_label(c["type"], self.screens)[:14] or "نوع", lambda i=i: choose_type(i), BLUE, 44, 0.42))
                lst.add_widget(r)
            self.build_bar()
        def change(fn): fn(); self.persist(); redraw()
        def count(d): change(lambda: WM.set_count(self.cfg, self.cfg["n"] + d))
        def choose_type(i):
            b = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6)); q = popup("اختر محتوى الخانة %d" % (i + 1), b, (0.94, 0.85)); g = scroll_grid(b)
            def add(title, pairs):
                g.add_widget(L(title, 30, color=(0.6, 0.8, 1, 1)))
                for t, label in pairs:
                    g.add_widget(B(label, lambda t=t: (q.dismiss(), change(lambda: WM.set_cell(self.cfg, i, t, screens=self.screens))), BLUE, 44))
            add("لوحات إعدادات", [("group:" + k, v[0]) for k, v in WM.GROUPS.items()])
            add("إعداد واحد في خانة", [("setting:" + k, v) for k, v in WM.SETTINGS.items()])
            add("أوامر سريعة", [("action:" + k, v) for k, v in WM.ACTIONS.items()])
            add("شاشات التطبيق", [("screen:" + k, v) for k, v in self.screens.items()])
            b.add_widget(B("إلغاء", q.dismiss, GREY))
        box.add_widget(B("تم", p.dismiss, GREEN))
        redraw()

# ---------- Split screen studio: independent zones, each with its own content ----------
def TL(text):
    """Arabic shaping line by line (a multi-line string must not be reordered as one paragraph)."""
    return "\n".join(T(x) for x in str(text).split("\n"))

ZONE_COLORS = {"empty": "#37474F", "image": "#1B5E20", "video": "#0D47A1", "text": "#4A148C", "slideshow": "#E65100", "ticker": "#00695C"}
ZONE_FIT = {"احتواء": "contain", "تغطية": "cover", "تمديد": "fill", "تصغير فقط": "scale-down"}
ZONE_ALIGN = {"يمين": "right", "وسط": "center", "يسار": "left"}
ZONE_TRANS = {"بدون": "none", "تلاشي": "fade", "انزلاق لليسار": "slide_left", "انزلاق لليمين": "slide_right"}
ZONE_TDIR = {"من اليمين لليسار": "r2l", "من اليسار لليمين": "l2r"}
ZONE_GRID = {"1": 1, "2": 2, "3": 3}
CONTENT_KEYS = ZN.CONTENT_KEYS

class ZoneTile(FloatLayout):
    """One zone in the preview. Tap = select it."""
    def __init__(self, z, selected, on_tap, thumbfn=None, **kw):
        super().__init__(size_hint=(z["w"], z["h"]), pos_hint={"x": z["x"], "y": z["y"]}, **kw)
        self.zid = z["id"]; self.on_tap = on_tap
        with self.canvas.before:
            Color(*H(ZONE_COLORS[z["kind"]])); self._r = Rectangle(pos=self.pos, size=self.size)
        with self.canvas.after:
            Color(*(H("#FFEB3B") if selected else H("#90A4AE"))); self._l = Line(rectangle=(0, 0, 1, 1), width=dp(3) if selected else dp(1))
        self.bind(pos=self._u, size=self._u)
        thumb = z.get("path") if z["kind"] == "image" and z.get("src") == "local" else None
        if z["kind"] == "slideshow":
            thumb = next((i["path"] for i in z["items"] if i.get("src") == "local" and i.get("path")), None)
        if thumb and os.path.isfile(thumb):
            self.add_widget(Image(source=(thumbfn(thumb) if thumbfn else thumb), size_hint=(1, 1)))
        lbl = Label(text=TL("%s\n%s" % (ZN.zone_label(z), ZN.summary(z))), color=(1, 1, 1, 1), font_size="12sp",
                    halign="center", valign="middle", size_hint=(1, 1), **F)
        lbl.bind(size=lambda i, v: setattr(i, "text_size", (v[0] * 0.9, v[1])))
        self.add_widget(lbl)
    def _u(self, *a):
        self._r.pos, self._r.size = self.pos, self.size
        self._l.rectangle = (self.x, self.y, self.width, self.height)
    def on_touch_down(self, t):
        if self.collide_point(*t.pos):
            self.on_tap(self.zid); return True
        return super().on_touch_down(t)


class ZoneStudio(Page):
    """Pick a layout (full / 2 columns / 2 rows / 3 columns / main+sidebar / 4 zones / custom grid), resize it, give every
    zone its own image, video, text, slideshow or news ticker, and control each zone separately from the Sender."""
    def __init__(self, app):
        super().__init__(app, "zones", "تقسيم الشاشة")
        st = app.store.d["settings"].get("zones") or {}
        ids = ZN.template_ids()
        self.tid = st.get("tid") if st.get("tid") in ids else "split-vertical"
        self.cols = int(ZN._num(st.get("cols"), 1, 3, 3)); self.rows = int(ZN._num(st.get("rows"), 1, 3, 2))
        self.ratios = ZN.clamp_ratios(self.tid, st.get("ratios") if isinstance(st.get("ratios"), dict) else ZN.default_ratios(self.tid))
        base = ZN.layout_zones(self.tid, self.ratios, self.cols, self.rows); zs = ZN.normalize_zones(st.get("zones"))
        self.zones = ZN.regeometry(zs, base) if {z["id"] for z in zs} == {z["id"] for z in base} else base
        self.sel = self.zones[0]["id"]; self.portrait = bool(st.get("portrait", True)); self._vol = None; self.sent_sig = None
        sv = ScrollView(); self.col = GridLayout(cols=1, size_hint_y=None, spacing=dp(6), padding=dp(2))
        self.col.bind(minimum_height=self.col.setter("height")); sv.add_widget(self.col); self.body.add_widget(sv)
        self.tbox = GridLayout(cols=3, size_hint_y=None, spacing=dp(4)); self.col.add_widget(self.tbox)
        self.lbox = GridLayout(cols=1, size_hint_y=None, spacing=dp(4)); self.lbox.bind(minimum_height=self.lbox.setter("height")); self.col.add_widget(self.lbox)
        self.pvbox = FloatLayout(size_hint_y=None, height=dp(270)); self.col.add_widget(self.pvbox)
        self.pv = FloatLayout(size_hint=(None, None))
        with self.pv.canvas.before:
            Color(0, 0, 0, 1); self._pr = Rectangle()
        self.pv.bind(pos=lambda i, v: setattr(self._pr, "pos", v), size=lambda i, v: setattr(self._pr, "size", v))
        self.pvbox.add_widget(self.pv); self.pvbox.bind(pos=self.fit, size=self.fit)
        self.ebox = GridLayout(cols=1, size_hint_y=None, spacing=dp(6)); self.ebox.bind(minimum_height=self.ebox.setter("height"))
        self.col.add_widget(self.ebox)
        act = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(4))
        act.add_widget(B("إرسال التقسيم كاملاً", self.send_all, GREEN, 50)); act.add_widget(B("تحديث المنطقة المحددة فقط", self.send_zone, BLUE, 50))
        self.body.add_widget(act)
        act2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        act2.add_widget(B("حفظ التقسيم", self.save_dialog, GREY, 44)); act2.add_widget(B("فتح تقسيم محفوظ", self.open_dialog, GREY, 44))
        self.body.add_widget(act2)
        self.redraw()

    # ---- state
    def zone(self): return ZN.find(self.zones, self.sel)
    def layout(self): return {"ratios": self.ratios, "cols": self.cols, "rows": self.rows}
    def persist(self):
        self.app.store.d["settings"]["zones"] = {"tid": self.tid, "zones": copy.deepcopy(self.zones), "portrait": self.portrait,
                                                 "ratios": self.ratios, "cols": self.cols, "rows": self.rows}
        self.app.store.save()
    def payload(self): return ZN.zone_scene(self.tid, self.zones, "#000000", self.layout())
    def upd(self, redraw=False, **kw):
        z = self.zone()
        if z is None: return
        self.zones = ZN.set_content(self.zones, self.sel, **{**{k: z[k] for k in CONTENT_KEYS}, **kw})
        self.persist(); self.draw_preview()
        if redraw: self.draw_editor()
    def select(self, zid):
        self.sel = zid; self.draw_preview(); self.draw_editor()
    def set_template(self, tid):
        if tid == self.tid: return
        self.tid = tid; self.ratios = ZN.default_ratios(tid)
        new = ZN.layout_zones(tid, self.ratios, self.cols, self.rows)
        self.zones = ZN.regeometry(self.zones, new, by="index")     # contents keep their order in the new layout
        self.sel = self.zones[0]["id"]; self.persist(); self.redraw()
    def resize(self, **kw):
        """Change the layout parameters (ratios / grid size) keeping every zone's content."""
        if "cols" in kw: self.cols = kw["cols"]
        if "rows" in kw: self.rows = kw["rows"]
        if any(k in kw for k in ("a", "b")): self.ratios = ZN.clamp_ratios(self.tid, {**self.ratios, **{k: v for k, v in kw.items() if k in ("a", "b")}})
        new = ZN.layout_zones(self.tid, self.ratios, self.cols, self.rows)
        self.zones = ZN.regeometry(self.zones, new, by="id")
        if self.sel not in {z["id"] for z in self.zones}: self.sel = self.zones[0]["id"]
        self.persist(); self.draw_preview()
        if "cols" in kw or "rows" in kw: self.draw_editor()
    def set_media(self, kind, item):
        mute = False
        if kind == "video":                                           # only one video should make sound
            mute = any(z["kind"] == "video" and not z["mute"] and z["id"] != self.sel for z in self.zones)
        self.upd(redraw=True, kind=kind, src=item.get("src", ""), name=item.get("name", ""), path=item.get("path", ""),
                 uri=item.get("uri", ""), loop=True, mute=mute, volume=100)
        self.app.toast("تم اختيار: %s" % item.get("name", ""))
    def pick(self, kind): self.app.choose_media(kind, lambda it: self.set_media(kind, it))
    def make_text(self):
        z = self.zone(); self.upd(redraw=True, kind="text", src="", name="", path="", uri="", text=z["text"] or "اكتب النص هنا")
    def make_ticker(self):
        z = self.zone()
        self.upd(redraw=True, kind="ticker", src="", name="", path="", uri="", text=z["text"] or "أخبار عاجلة: اكتب الخبر هنا",
                 size=0.3 if z["kind"] != "ticker" else z["size"])
    def add_slide(self, item):
        z = self.zone()
        if len(z["items"]) >= ZN.MAX_SLIDES: return self.app.toast("وصلت إلى الحد الأقصى للصور (%d)" % ZN.MAX_SLIDES)
        it = {"src": item.get("src", ""), "name": item.get("name", ""), "path": item.get("path", ""), "uri": item.get("uri", ""), "kind": "image"}
        self.upd(redraw=True, kind="slideshow", src="", name="", path="", uri="", items=z["items"] + [it])
        self.app.toast("تمت إضافة: %s" % item.get("name", ""))
    def del_slide(self, i):
        z = self.zone(); items = [x for n, x in enumerate(z["items"]) if n != i]
        self.upd(redraw=True, items=items, kind="slideshow" if items else "empty")
    def clear(self): self.upd(redraw=True, kind="empty", src="", name="", path="", uri="", text="", items=[])

    # ---- live control of a video zone
    def ctl(self, action, value=0):
        z = self.zone()
        if z and z["kind"] == "video": self.app.send("zone_ctl", {"zone": z["id"], "action": action, "value": int(value)})
    def set_mute(self, on):
        self.upd(mute=on); self.ctl("mute" if on else "unmute")
    def set_volume(self, v):
        self.upd(volume=int(v), mute=False)
        if self._vol: self._vol.cancel()
        self._vol = Clock.schedule_once(lambda dt: self.ctl("volume", v), 0.5)

    # ---- drawing
    def refresh(self): self.redraw()
    def redraw(self): self.draw_templates(); self.draw_layout(); self.draw_preview(); self.draw_editor()
    def draw_templates(self):
        self.tbox.clear_widgets()
        names = {t["id"]: t["name"] for t in ZN.TPL.load_templates()}; names[ZN.CUSTOM] = "شبكة مخصصة"
        ids = ZN.template_ids(); rows = (len(ids) + 2) // 3
        self.tbox.height = dp(46) * rows + dp(4) * (rows - 1)
        for tid in ids:
            b = B(names[tid], lambda tid=tid: self.set_template(tid), GREEN if tid == self.tid else GREY, 46)
            b.font_size = "13sp"; b.halign = "center"; b.valign = "middle"
            b.bind(size=lambda i, v: setattr(i, "text_size", (v[0] - dp(6), v[1]))); self.tbox.add_widget(b)
    def draw_layout(self):
        """Resizing controls: sliders for the layout's ratios, or columns/rows for the custom grid."""
        self.lbox.clear_widgets()
        if self.tid == ZN.CUSTOM:
            for label, key, cur in (("عدد الأعمدة", "cols", self.cols), ("عدد الصفوف", "rows", self.rows)):
                sp = SP(T(str(cur)), [T(k) for k in ZONE_GRID])
                sp.bind(text=lambda i, v, key=key: self.resize(**{key: ZN._num(v, 1, 3, 2) and int(ZN._num(v, 1, 3, 2))}))
                self.lbox.add_widget(self._row(label, sp))
            return
        for key, label, lo, hi, d in ZN.params_for(self.tid):
            sl = Slider(min=lo, max=hi, value=float(self.ratios.get(key, d)))
            sl.bind(value=lambda i, v, key=key: self.resize(**{key: v})); self.lbox.add_widget(self._row(label, sl))
        if self.lbox.children: self.lbox.add_widget(L("بعد تغيير المقاسات يُرسَل التقسيم كاملاً مرة أخرى", 26, font_size="12sp"))
    def fit(self, *a):
        W, Hh = self.pvbox.size
        if W <= 0 or Hh <= 0: return
        ratio = 9 / 16 if self.portrait else 16 / 9
        w = min(W, Hh * ratio); h = w / ratio
        self.pv.size = (w, h); self.pv.pos = (self.pvbox.x + (W - w) / 2, self.pvbox.y + (Hh - h) / 2)
    def draw_preview(self):
        self.pv.clear_widgets()
        for z in self.zones: self.pv.add_widget(ZoneTile(z, z["id"] == self.sel, self.select, thumbfn=self.app.thumb_path))
        self.fit()
    def flip(self): self.portrait = not self.portrait; self.persist(); self.fit()
    def draw_editor(self):
        e = self.ebox; e.clear_widgets(); z = self.zone()
        if z is None: return
        e.add_widget(L("المنطقة المحددة: %s" % ZN.zone_label(z), 34, font_size="17sp", color=(1, 0.92, 0.23, 1)))
        for names in ((("صورة", lambda: self.pick("image"), BLUE), ("فيديو", lambda: self.pick("video"), BLUE), ("نص", self.make_text, BLUE)),
                      (("عرض صور", lambda: self.app.choose_media("image", self.add_slide), BLUE), ("شريط أخبار", self.make_ticker, BLUE),
                       ("تفريغ", self.clear, RED))):
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3))
            for name, cb, col in names: row.add_widget(B(name, cb, col, 48))
            e.add_widget(row)
        k = z["kind"]
        if k == "image":
            e.add_widget(self._row("طريقة العرض", self._spinner(z, "fit", ZONE_FIT, "contain")))
        elif k == "video":
            self._video_editor(e, z)
        elif k == "text":
            self._text_editor(e, z)
        elif k == "ticker":
            self._ticker_editor(e, z)
        elif k == "slideshow":
            self._slides_editor(e, z)
        else:
            e.add_widget(L("المنطقة فارغة. اختر صورة أو فيديو أو نصاً أو عرض صور أو شريط أخبار.", 40))
        e.add_widget(B("شكل المعاينة: " + ("رأسي" if self.portrait else "أفقي") + " (اضغط للتبديل)", self.flip, GREY, 40))
    def _video_editor(self, e, z):
        tl = ToggleButton(text=T("تكرار الفيديو"), state="down" if z["loop"] else "normal", size_hint_y=None, height=dp(44), **F)
        tm = ToggleButton(text=T("كتم الصوت"), state="down" if z["mute"] else "normal", size_hint_y=None, height=dp(44), **F)
        tl.bind(state=lambda i, s: self.upd(loop=(s == "down"))); tm.bind(state=lambda i, s: self.set_mute(s == "down"))
        r2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3)); r2.add_widget(tl); r2.add_widget(tm); e.add_widget(r2)
        sl = Slider(min=0, max=100, value=float(z["volume"]), step=5); sl.bind(value=lambda i, v: self.set_volume(v)); e.add_widget(self._row("مستوى الصوت", sl))
        r3 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        for name, act in (("إيقاف مؤقت", "pause"), ("استئناف", "resume"), ("من البداية", "restart")):
            r3.add_widget(B(name, lambda a=act: self.ctl(a), GREY, 44))
        e.add_widget(r3); e.add_widget(L("أزرار الإيقاف والاستئناف تعمل فوراً على جهاز العرض دون إرسال جديد", 26, font_size="12sp"))
    def _text_editor(self, e, z):
        ti = TI(z["text"], "نص المنطقة", ml=True, h=100); ti.bind(text=lambda i, t: self.upd(text=t)); e.add_widget(ti)
        e.add_widget(self._color_row("لون النص", "color")); e.add_widget(self._color_row("لون الخلفية", "bg"))
        sl = Slider(min=.04, max=.4, value=float(z["size"])); sl.bind(value=lambda i, v: self.upd(size=v)); e.add_widget(self._row("حجم الخط", sl))
        e.add_widget(self._row("المحاذاة", self._spinner(z, "align", ZONE_ALIGN, "center")))
    def _ticker_editor(self, e, z):
        ti = TI(z["text"], "نص الشريط (كل سطر خبر)", ml=True, h=100); ti.bind(text=lambda i, t: self.upd(text=t)); e.add_widget(ti)
        e.add_widget(self._color_row("لون النص", "color")); e.add_widget(self._color_row("لون الخلفية", "bg"))
        sz = Slider(min=.05, max=.5, value=float(z["size"])); sz.bind(value=lambda i, v: self.upd(size=v)); e.add_widget(self._row("حجم الخط", sz))
        sp = Slider(min=1, max=10, value=float(z["speed"]), step=1); sp.bind(value=lambda i, v: self.upd(speed=int(v))); e.add_widget(self._row("السرعة", sp))
        e.add_widget(self._row("الاتجاه", self._spinner(z, "tdir", ZONE_TDIR, "r2l")))
    def _slides_editor(self, e, z):
        e.add_widget(L("الصور (%d): تتبدل تلقائياً بالترتيب" % len(z["items"]), 30))
        for n, it in enumerate(z["items"]):
            r = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(3))
            r.add_widget(B("×", lambda n=n: self.del_slide(n), RED, 40, 0.15)); r.add_widget(L("%d. %s" % (n + 1, it["name"][:30]), halign="right")); e.add_widget(r)
        sl = Slider(min=2, max=60, value=float(z["secs"]), step=1); sl.bind(value=lambda i, v: self.upd(secs=int(v))); e.add_widget(self._row("الثواني لكل صورة", sl))
        e.add_widget(self._row("الانتقال", self._spinner(z, "trans", ZONE_TRANS, "fade")))
        e.add_widget(self._row("طريقة العرض", self._spinner(z, "fit", ZONE_FIT, "contain")))
    def _row(self, label, widget, h=44):
        row = BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(4)); row.add_widget(L(label, size_hint_x=.32, halign="right")); row.add_widget(widget); return row
    def _spinner(self, z, key, mapping, default):
        nm = next((n for n, v in mapping.items() if v == z[key]), next(iter(mapping))); sp = SP(T(nm), [T(n) for n in mapping])
        sp.bind(text=lambda i, v: self.upd(**{key: pick(mapping, v, default)})); return sp
    def _color_row(self, label, key):
        z = self.zone(); b = Button(background_normal="", background_color=H(z[key]))
        def done(v): self.upd(**{key: v}); b.background_color = H(v)
        b.bind(on_release=lambda *_: pick_color(label, self.zone()[key], done)); return self._row(label, b)

    # ---- sending
    def send_all(self):
        self.sent_sig = ZN.geometry_sig(self.zones)
        self.app.send_scene(self.payload(), "سيتم استبدال المعروض على جهاز العرض بالتقسيم الجديد. متابعة؟")
    def send_zone(self):
        z = self.zone()
        if z is None: return
        if not self.app.is_ready(): return self.app.toast("غير متصل بجهاز العرض")
        if self.sent_sig is not None and self.sent_sig != ZN.geometry_sig(self.zones):
            self.app.toast("تغيّرت المقاسات: يلزم إرسال التقسيم كاملاً"); return self.send_all()
        self.app.toast("جاري التجهيز...")
        self.app.resolve_scenes([{"zones": [z]}], lambda out: self.app.send("zone_set", {"zone": out[0]["zones"][0]}), self.app.toast)

    # ---- saved layouts (stored with the other saved scenes, so they also work in playlists and projects)
    def save_dialog(self):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6)); ti = TI("تقسيم " + time.strftime("%H:%M")); box.add_widget(ti)
        p = popup("اسم التقسيم", box, (0.9, 0.4)); row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        def save():
            p.dismiss(); self.app.store.put("scenes", {"name": ti.text.strip() or "تقسيم", "scene": self.payload()}); self.app.toast("تم حفظ التقسيم")
        row.add_widget(B("إلغاء", p.dismiss, GREY)); row.add_widget(B("حفظ", save, GREEN)); box.add_widget(row)
    def open_dialog(self):
        b = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6)); p = popup("التقسيمات المحفوظة", b, (0.94, 0.8)); g = scroll_grid(b)
        items = [it for it in self.app.store.items("scenes", "") if isinstance(it.get("scene"), dict) and it["scene"].get("zones")]
        if not items: g.add_widget(L("لا توجد تقسيمات محفوظة بعد", 40))
        for it in items:
            g.add_widget(B(it.get("name", "تقسيم")[:34], lambda it=it: (p.dismiss(), self.load_scene(it["scene"])), BLUE, 48))
        b.add_widget(B("إغلاق", p.dismiss, GREY))
    def load_scene(self, sc):
        zs = ZN.normalize_zones(sc.get("zones"))
        if not zs: return self.app.toast("لا يوجد تقسيم في هذا المشهد")
        tid = sc.get("template_id") if sc.get("template_id") in ZN.template_ids() else None
        if tid is None: tid = ZN.CUSTOM if ZN.infer_grid(zs) != (1, 1) and zs[0]["id"].startswith("r") else "full"
        lay = sc.get("layout") if isinstance(sc.get("layout"), dict) else {}
        self.tid = tid; self.zones = zs
        self.ratios = ZN.clamp_ratios(tid, lay.get("ratios") or ZN.infer_ratios(tid, zs))
        self.cols, self.rows = ZN.infer_grid(zs) if tid == ZN.CUSTOM else (int(ZN._num(lay.get("cols"), 1, 3, self.cols)), int(ZN._num(lay.get("rows"), 1, 3, self.rows)))
        self.sel = zs[0]["id"]; self.sent_sig = None; self.persist(); self.redraw(); self.app.toast("تم فتح التقسيم")

# ---------- app ----------
class SenderApp(App):
    def build(self):
        Window.clearcolor = H(DARK)
        self.store = Store(os.path.join(self.user_data_dir, "data.json"))
        self.fdir = os.path.join(self.user_data_dir, "fonts"); os.makedirs(self.fdir, exist_ok=True)
        self.bdir = os.path.join(self.user_data_dir, "backups"); os.makedirs(self.bdir, exist_ok=True)
        self.mdir = os.path.join(self.user_data_dir, "media"); os.makedirs(self.mdir, exist_ok=True)
        self.fonts = {}; self.scan_fonts()
        self.ble = None; self.act = None; self.mh = None; self.rinfo = None; self.said_hello = False; self.loc_ok = None; self._wifi_t = 0.0
        self.sec = SF.SenderSecurity(os.path.join(self.user_data_dir, "secure.json")); self.waiters = {}
        self.want = False; self.rc_next = 0.0; self.rc_wait = 2.0; self._st = None; self._st_t = time.time()
        self.level = 1.0; self.pad_hidden = False; self.media_state = {}
        self.ra = Reassembler(); self.pending = {}; self.fired = set(); self.msg = ""
        root = FloatLayout()
        self.bgimg = Image(allow_stretch=True, keep_ratio=False, size_hint=(1, 1), opacity=0)
        self.dim = Widget(size_hint=(1, 1), opacity=0)
        with self.dim.canvas:
            Color(0, 0, 0, 0.55); self.dr = Rectangle()
        self.dim.bind(pos=lambda i, v: setattr(self.dr, "pos", v), size=lambda i, v: setattr(self.dr, "size", v))
        root.add_widget(self.bgimg); root.add_widget(self.dim)
        self.sm = ScreenManager(transition=NoTransition()); root.add_widget(self.sm)
        self.status = L("غير متصل", 30)
        self.status2 = L("غير متصل", 30); self.status.bind(text=lambda i, v: setattr(self.status2, "text", v))
        home = Screen(name="all"); hb = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        hb.add_widget(L("WALIBRA — كل الميزات", 40, font_size="22sp")); hb.add_widget(self.status2)
        hb.add_widget(B("رجوع للشاشة الرئيسية", lambda: self.go("home"), GREY, 44))
        g = GridLayout(cols=2, spacing=dp(6), size_hint_y=None); g.bind(minimum_height=g.setter("height"))
        hsv = ScrollView(); hsv.add_widget(g); hb.add_widget(hsv); home.add_widget(hb); self.sm.add_widget(home)
        memo_f = [("name", "الاسم", False), ("folder", "المجلد/التصنيف", False), ("body", "النص", True)]
        self.proj_edit = ProjectEditor(self)
        pages = [
            ("content", "مدير المحتوى المتقدم", ContentHub(self)),
            ("text_manager", "إدارة النصوص", TextHub(self)),
            ("design_hub", "استديو التصميم", DesignHub(self)),
            ("emergency", "وضع الطوارئ", EmergencyPage(self)),
            ("zones", "تقسيم الشاشة", ZoneStudio(self)),
            ("designer", "مصمم الشاشة", Designer(self)), ("text", "استوديو النصوص", TextStudio(self)),
            ("fonts", "مكتبة الخطوط", Fonts(self)),
            ("memos", "إدارة المذكرات", ListPage(self, "memos", "إدارة المذكرات", "memos", memo_f, send=self.send_memo)),
            ("media", "استوديو الوسائط", MediaPage(self)),
            ("commands", "مركز الأوامر النصية", CommandCenter(self)),
            ("remote", "التحكم عن بعد", Remote(self)),
            ("touch", "التحكم باللمس", Soon(self, "touch", "التحكم باللمس", "يتطلب تفعيل خدمة إمكانية الوصول على جهاز العرض — مرحلة لاحقة")),
            ("live", "البث المباشر", Soon(self, "live", "البث المباشر", "يتطلب إذن تسجيل الشاشة واتصال الواي فاي — مرحلة لاحقة")),
            ("voice", "التحكم الصوتي", Soon(self, "voice", "التحكم الصوتي", "الأوامر الصوتية: مرحلة لاحقة")),
            ("templates", "القوالب", ListPage(self, "templates", "القوالب", "templates",
                [("name", "الاسم", False), ("body", "بيانات التصميم", True)], extra=("فتح", self.open_design))),
            ("playlists", "قوائم التشغيل", ListPage(self, "playlists", "قوائم التشغيل", "playlists",
                [("name", "الاسم", False), ("items", "أسماء المذكرات (سطر لكل عنصر)", True), ("secs", "ثواني لكل عنصر", False)],
                send=self.send_playlist)),
            ("sched", "الجدولة", ListPage(self, "sched", "الجدولة", "schedules",
                [("name", "الاسم", False), ("memo", "اسم المذكرة", False), ("when", "الموعد (سنة-شهر-يوم ساعة:دقيقة) مثل 2026-11-05 14:30", False)])),
            ("news", "استوديو النصوص والأخبار", NewsStudio(self)),
            ("tplv8", "قوالب الأخبار والإعلانات", TemplatesV8(self)),
            ("scenes_v8", "المشاهد المحفوظة", ListPage(self, "scenes_v8", "المشاهد المحفوظة", "scenes", [("name", "الاسم", False)],
                send=lambda it: self.send_scene(it["scene"]), extra=("فتح", lambda it: (self.sm.get_screen("news").load_scene(it["scene"]), self.go("news"))))),
            ("devices", "إدارة الأجهزة", Devices(self)),
            ("rbrowser", "متصفح جهاز العرض", ReceiverBrowser(self)),
            ("files", "مدير ملفات جهاز العرض", FileManager(self)),
            ("pad", "لوحة الإيماءات", GesturePad(self)),
            ("projects", "المشاريع", ListPage(self, "projects", "المشاريع", "projects",
                [("name", "الاسم", False), ("secs", "مدة كل مشهد بالثواني", False)],
                extra=("فتح", lambda it: self.proj_edit.open(it)))),
            ("backup", "النسخ الاحتياطي", Backup(self)), ("settings", "الإعدادات", Settings(self)),
            ("pages", "الصفحات", ListPage(self, "pages", "الصفحات", "pages",
                [("name", "الاسم", False), ("body", "بيانات التصميم", True)], extra=("فتح", self.open_design),
                send=self.send_page)),
        ]
        self.sm.add_widget(self.proj_edit)
        for key, title, scr in pages:
            self.sm.add_widget(scr)
            g.add_widget(B(title, lambda k=key: self.go(k), BLUE, 56))
        self.designer = self.sm.get_screen("designer")
        self.page_titles = {key: title for key, title, _ in pages}
        self.ws = None
        try:
            self.ws = Workspace(self); self.sm.add_widget(self.ws); self.sm.current = "home"
        except Exception as e:                      # never lose the app because of the new screen: fall back to the full list
            self.ws = None; self.sm.current = "all"; self.status.text = T("تعذر فتح الشاشة الرئيسية الجديدة: %s" % e)
        self.apply_appearance()
        self.apply_bg(self.store.d["settings"].get("bg", ""))
        return root

    # navigation / helpers
    def go(self, k): self.sm.current = ("all" if k == "home" and not self.ws else k)
    def toast(self, m): self.msg = m; self.status.text = T(m)
    def toast_later(self, m): Clock.schedule_once(lambda dt: self.toast(m), 0)
    def scan_fonts(self):
        self.fonts = {}
        for d in ("fonts", self.fdir):
            for f in glob.glob(os.path.join(d, "*.[to]tf")):
                self.fonts[os.path.splitext(os.path.basename(f))[0]] = f
    def sdk(self):
        """Android API level of this phone (99 when unknown, e.g. on a computer)."""
        if not hasattr(self, "_sdk"):
            try:
                from jnius import autoclass
                self._sdk = int(autoclass("android.os.Build$VERSION").SDK_INT)
            except Exception: self._sdk = 99
        return self._sdk
    def on_resume(self):
        """Back from the system settings: re-check the Location permission (Android 10/11 cannot scan without it)."""
        if self.sdk() < 31 and self.loc_ok is False:
            try:
                from android.permissions import check_permission
                self.loc_ok = bool(check_permission(LOCATION))
            except Exception: pass
        return True
    def ble_state(self):
        try: st = str(self.ble.getState()) if self.ble else "idle"
        except Exception: return "error"
        if self.loc_ok is False and st in ("idle", "scanning", "scan_failed"): return "perm_denied"   # Android 10 scans silently return nothing
        return st
    def wifi_bind(self, force=False):
        """Android may send local-network traffic over mobile data when the Wi-Fi has no internet; pin this app to the Wi-Fi."""
        now = time.time()
        if not self.mh or (not force and now - self._wifi_t < 20): return
        self._wifi_t = now
        try: self.mh.bindWifi(self.act)
        except Exception: pass
    def thumb_path(self, path, px=360):
        """Small JPEG copy of a photo for previews: decoding a 12 MP photo for every preview can exhaust a 2-3 GB phone."""
        try:
            if not path or not os.path.isfile(path) or not self.mh: return path
            d = os.path.join(self.mdir, ".thumbs"); os.makedirs(d, exist_ok=True)
            out = os.path.join(d, hashlib.md5(("%s|%s|%d" % (path, os.path.getmtime(path), px)).encode()).hexdigest() + ".jpg")
            if os.path.isfile(out): return out
            r = str(self.mh.makeThumb(path, out, int(px)))
            return r if r and os.path.isfile(r) else path
        except Exception: return path
    def status_text(self): return STATES.get(self.ble_state(), "") if self.ble else "غير جاهز"
    def chunk(self):
        try: return int(self.ble.chunkSize()) if self.ble else 0
        except Exception: return 0
    def is_ready(self): return bool(self.ble) and self.ble_state() == "ready"

    def apply_appearance(self):
        """Apply saved background/accent colors without rebuilding active editors."""
        settings = self.store.d.get("settings", {})
        bg = settings.get("ui_bg", DARK); accent = settings.get("ui_accent", BASE_BLUE)
        try:
            Window.clearcolor = H(bg)
        except Exception:
            Window.clearcolor = H(DARK)
        old = getattr(self, "_last_accent", BASE_BLUE)
        old_rgb = tuple(round(x, 3) for x in H(old)[:3])
        base_rgb = tuple(round(x, 3) for x in H(BASE_BLUE)[:3])
        new_color = H(accent)
        globals()["BLUE"] = accent
        def visit(widget):
            if isinstance(widget, Button):
                try:
                    rgb = tuple(round(x, 3) for x in widget.background_color[:3])
                    if rgb in (old_rgb, base_rgb): widget.background_color = new_color
                except Exception:
                    pass
            for child in getattr(widget, "children", []): visit(child)
        if getattr(self, "sm", None): visit(self.sm)
        self._last_accent = accent

    def apply_bg(self, path):
        ok = bool(path) and os.path.isfile(path)
        self.bgimg.source = path if ok else ""; self.bgimg.opacity = 1 if ok else 0; self.dim.opacity = 1 if ok else 0
    def set_bg(self, path):
        if path:
            ext = os.path.splitext(path)[1] or ".jpg"
            dest = os.path.join(self.user_data_dir, "app_bg_%d%s" % (int(time.time()), ext)); shutil.copy(path, dest); path = dest
        self.store.d["settings"]["bg"] = path; self.store.save(); self.apply_bg(path)
        self.toast("تم تغيير خلفية التطبيق" if path else "تمت إزالة الخلفية")

    # ---- lifecycle
    def on_start(self):
        try:
            from jnius import autoclass
            self.act = autoclass("org.kivy.android.PythonActivity").mActivity
            self.mh = autoclass("org.bleremote.MediaHelper")
        except Exception: pass
        pin = self.store.d["settings"].get("pin")
        if pin: self.ask_pin(pin)
        try:
            from android.permissions import request_permissions
            def granted(perms, grants):
                if self.sdk() < 31: self.loc_ok = any(str(p).endswith("ACCESS_FINE_LOCATION") and bool(ok) for p, ok in zip(perms, grants))
                Clock.schedule_once(self.init_ble, 0)
            request_permissions(PERMS if self.sdk() >= 31 else PERMS_LEGACY, granted)
        except Exception: self.init_ble()
        Clock.schedule_interval(self.check_schedule, 15)

    def ask_pin(self, h):
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        ti = TI(hint="الرمز السري", password=True); box.add_widget(L("أدخل الرمز السري")); box.add_widget(ti)
        p = Popup(title=T("الرمز السري"), title_font=APP_FONT if F else "Roboto", content=box, size_hint=(.9, .4), auto_dismiss=False)
        def ok():
            if hashlib.sha256(ti.text.encode()).hexdigest() == h: p.dismiss()
            else: ti.text = ""
        box.add_widget(B("دخول", ok, GREEN)); p.open()

    def init_ble(self, *a):
        try:
            from jnius import autoclass
            self.ble = autoclass("org.bleremote.BleClient")(self.act)
            Clock.schedule_interval(self.tick, 0.1)
            if self.store.d["settings"].get("auto_connect"): self.connect()
        except Exception as e: self.status.text = T("خطأ البلوتوث: %s" % e)

    def connect(self):
        self.want = True; self.rc_wait = 2.0
        if self.ble:
            try: self.ble.connect()
            except Exception as e: self.toast("تعذر بدء البحث: %s" % e)
    def disconnect(self):
        self.want = False
        if self.ble:
            try: self.ble.close()
            except Exception as e: print("close:", e)
    def toggle_auto(self):
        s = self.store.d["settings"]; s["auto_connect"] = not s.get("auto_connect"); self.store.save()
        self.toast("الاتصال التلقائي: " + ("تشغيل" if s["auto_connect"] else "إيقاف"))
    def rcall(self, method, path):
        r = self.rinfo
        if not r: raise RuntimeError("اتصل أولاً")
        self.wifi_bind()
        c = http.client.HTTPConnection(r["ip"], r["port"], timeout=15)
        try:
            c.request(method, path + ("&" if "?" in path else "?") + "t=" + r["token"])
            resp = c.getresponse(); return resp.status, json.loads(resp.read() or b"{}")
        finally: c.close()
    def auto_reconnect(self):
        st = self.ble_state(); now = time.time()
        if st != self._st: self._st, self._st_t = st, now
        if st == "ready": self.rc_wait = 2.0; return
        stuck = st in ("scanning", "connecting") and now - self._st_t > 25
        if self.want and (stuck or st in ("disconnected", "scan_failed", "no_service", "idle", "error", "location_off", "perm_denied", "bt_off")) and now >= self.rc_next:
            self.rc_next = now + self.rc_wait; self.rc_wait = min(30.0, self.rc_wait * 2)
            self._st_t = now
            try: self.ble.connect()                      # a Java exception here used to close the whole app
            except Exception as e: print("reconnect:", e)

    def tick(self, dt):
        try: self._tick(dt)
        except Exception:
            import crashguard, traceback; crashguard.record("tick failed:\n" + traceback.format_exc())

    def _tick(self, dt):
        if not self.pending: self.status.text = T(self.msg or self.status_text())
        self.auto_reconnect()
        ready = self.is_ready()
        if ready and not self.said_hello:
            self.said_hello = True; self.send("hello", {})
        if not ready: self.said_hello = False
        for _ in range(20):
            raw = self.ble.poll()
            if raw is None: break
            m = self.sec.open_frame(self.ra.feed(to_bytes(raw)))        # V9: decrypts frames, ignores forged/replayed ones
            if m and m.get("t") == "ack":
                d = m["d"]
                waiter = self.waiters.pop(d.get("id"), None)
                if waiter: self.pending.pop(d.get("id"), None); waiter(d); continue
                what = self.pending.pop(d.get("id"), None)
                act = self.sec.note_hello(d)
                if act == "secure_hello" and not d.get("ip"): self.send("hello", {}, secure=True)
                elif act == "foreign": self.toast("الجهاز مقترن بمرسل آخر: ألغِ الاقتران منه أولاً")
                if d.get("media"):
                    try: self.media_state = json.loads(d["media"]); self.sm.get_screen("rbrowser").show_state()
                    except Exception: pass
                if what == TYPES["media"]: continue
                if d.get("ip"):
                    self.rinfo = {"ip": d["ip"], "port": d.get("port", 8765), "token": d.get("token", "")}; self.wifi_bind()
                result_text = str(d.get("result", ""))
                if result_text:
                    try:
                        page = self.sm.get_screen("commands")
                        page.result.text = T(result_text)
                    except Exception: pass
                if what:
                    ok = d.get("ok"); self.store.log(("✔ " if ok else "✘ ") + what)
                    if what == TYPES["hello"]: self.msg = "متصل ✔" + ("  |  " + self.rinfo["ip"] if self.rinfo else "")
                    elif result_text: self.msg = result_text
                    else: self.msg = "تم الاستلام والاعتماد ✔" if ok else "رفض جهاز العرض الأمر"
                    self.status.text = T(self.msg)

    # ---- sending (always explicit)
    def send(self, type_, data, secure=None, waiter=None):
        if not self.is_ready():
            self.toast("غير متصل بجهاز العرض"); return False
        try: mid, env = self.sec.build(type_, data, secure)
        except SF.X.SecureError: self.toast("الرسالة كبيرة جداً للإرسال المشفر"); return False
        if waiter: self.waiters[mid] = waiter
        self.pending[mid] = TYPES.get(type_, type_)
        try:
            for p in fragment(env, int(self.ble.chunkSize())): self.ble.send(p)
        except Exception as e:
            self.pending.pop(mid, None); self.waiters.pop(mid, None)
            self.toast("فشل الإرسال: %s" % e); return False
        if type_ != "media": self.store.log("→ " + TYPES.get(type_, type_))
        if type_ not in ("hello", "media"): self.status.text = T("جاري الإرسال...")
        return True

    # ---- V9: secure pairing (numbers must match on both screens)
    def start_pairing(self):
        if not self.is_ready(): return self.toast("اتصل بجهاز العرض أولاً")
        if self.sec.sess: return self.toast("مقترن بالفعل. ألغِ الاقتران أولاً")
        try: body = self.sec.start_pairing()
        except SF.X.SecureError: return self.toast("انتظر حتى يتعرف التطبيق على جهاز العرض ثم أعد المحاولة")
        self.send("pair_begin", body, secure=False, waiter=self._pair_reply)

    def _pair_reply(self, d):
        if not d.get("ok"): self.sec.cancel_pairing(); return self.toast(str(d.get("result", "رفض جهاز العرض الاقتران")))
        try: sas = self.sec.on_pair_reply(d)
        except SF.X.SecureError as e: self.sec.cancel_pairing(); return self.toast("فشل الاقتران: %s" % e)
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        box.add_widget(L("الرمز على هذا الجهاز", 28)); box.add_widget(L(sas, 90, font_size="48sp"))
        box.add_widget(L("هل يطابق الرمز الظاهر على جهاز العرض تماماً؟ إن لم يتطابق اضغط لا.", 70))
        p = popup("تأكيد الاقتران", box, (0.92, 0.6)); row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        row.add_widget(B("لا", lambda: (p.dismiss(), self.sec.cancel_pairing()), RED))
        row.add_widget(B("نعم، يتطابق", lambda: (p.dismiss(), self._pair_confirm(time.time() + SF.X.PAIR_WINDOW)), GREEN)); box.add_widget(row)
        self.toast("اضغط «قبول» على جهاز العرض بعد مطابقة الرمز")

    def _pair_confirm(self, until):
        if self.sec.sess or not self.sec.pairing or time.time() > until: return
        self.send("pair_confirm", self.sec.confirm_body(), secure=False, waiter=lambda d: self._pair_wait(d, until))

    def _pair_wait(self, d, until):
        if d.get("ok"): return self.toast("تم الاقتران الآمن ✔ — الاتصال مشفّر الآن")
        if str(d.get("result")) == "pending": return Clock.schedule_once(lambda dt: self._pair_confirm(until), 2)
        self.sec.cancel_pairing(); self.toast(str(d.get("result", "فشل الاقتران")))

    def unpair(self):
        if self.sec.sess and self.is_ready():
            confirm("إلغاء الاقتران وإعادة جهاز العرض للوضع المفتوح؟",
                    lambda: self.send("unpair", {}, waiter=lambda d: (self.sec.forget(), self.toast("تم إلغاء الاقتران")) if d.get("ok") else self.toast(str(d.get("result", "فشل")))))
        else:
            confirm("حذف مفتاح الاقتران من هذا الجهاز فقط؟ (إن بقي جهاز العرض مقترناً فاحذف بياناته من الإعدادات)",
                    lambda: (self.sec.forget(), self.toast("تم حذف المفتاح محلياً")))

    # ---- picking media from this phone's gallery
    def pick_local(self, kind, cb):
        if not self.act or not self.mh: return self.toast("متاح على الأندرويد فقط")
        from jnius import autoclass
        from android import activity
        Intent = autoclass("android.content.Intent")
        i = Intent(Intent.ACTION_OPEN_DOCUMENT); i.addCategory(Intent.CATEGORY_OPENABLE); i.setType(kind + "/*")
        def on_result(req, res, intent):
            if req != PICK_REQ: return
            activity.unbind(on_activity_result=on_result)
            if res != -1 or intent is None or intent.getData() is None: return
            uri = intent.getData().toString()
            self.toast("جاري نسخ الملف...")
            def work():
                name = str(self.mh.copyUri(self.act, uri, self.mdir))
                if name: Clock.schedule_once(lambda dt: cb(os.path.join(self.mdir, name)), 0)
                else: self.toast_later("تعذر قراءة الملف")
            threading.Thread(target=work, daemon=True).start()
        activity.bind(on_activity_result=on_result)
        self.act.startActivityForResult(i, PICK_REQ)

    def add_to_library(self, path, kind):
        if not any(m["path"] == path for m in self.store.d["media"]):
            self.store.put("media", {"name": os.path.basename(path), "path": path, "kind": kind,
                                     "size": os.path.getsize(path)})

    def item_local(self, path, kind): return {"kind": kind, "src": "local", "path": path, "name": os.path.basename(path)}

    def choose_media(self, kind, cb):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        p = popup("اختر مصدر " + KINDS[kind], box, (0.9, 0.55))
        def local(path): self.add_to_library(path, kind); cb(self.item_local(path, kind))
        box.add_widget(B("من معرض هذا الجوال", lambda: (p.dismiss(), self.pick_local(kind, local))))
        box.add_widget(B("من مكتبة التطبيق", lambda: (p.dismiss(), self.library_chooser(kind, cb)), GREY))
        box.add_widget(B("من معرض جهاز العرض", lambda: (p.dismiss(), self.remote_gallery(kind, cb)), GREY))
        box.add_widget(B("إلغاء", p.dismiss, RED))

    def library_chooser(self, kind, cb):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        p = popup("مكتبة التطبيق", box, (0.94, 0.8)); g = scroll_grid(box)
        items = [m for m in self.store.d["media"] if m["kind"] == kind]
        if not items: g.add_widget(L("لا توجد ملفات. أضف من استوديو الوسائط.", 40))
        for m in items:
            g.add_widget(B(m["name"][:34], lambda m=m: (p.dismiss(), cb(self.item_local(m["path"], kind))), BLUE, 48))
        box.add_widget(B("إغلاق", p.dismiss, GREY))

    def remote_gallery(self, kind, cb):
        if not self.rinfo: return self.toast("اتصل بجهاز العرض أولاً (ويجب أن يكونا على نفس الواي فاي)")
        ip, port, tok = self.rinfo["ip"], self.rinfo["port"], self.rinfo["token"]
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        p = popup("معرض جهاز العرض", box, (0.94, 0.85)); g = scroll_grid(box)
        g.add_widget(L("جاري التحميل...", 40)); box.add_widget(B("إغلاق", p.dismiss, GREY))
        def work():
            try:
                c = http.client.HTTPConnection(ip, port, timeout=15)
                c.request("GET", "/list?t=" + tok); items = json.loads(c.getresponse().read())
                items = sorted([i for i in items if i.get("kind") == kind], key=lambda i: -i.get("date", 0))
                Clock.schedule_once(lambda dt: show(items), 0)
            except Exception as e:
                msg = "تعذر الوصول لجهاز العرض عبر الواي فاي: %s" % e
                Clock.schedule_once(lambda dt: (g.clear_widgets(), g.add_widget(L(msg, 60))), 0)
        def show(items):
            g.clear_widgets()
            if not items: g.add_widget(L("لا توجد ملفات من هذا النوع", 40))
            for it in items:
                row = BoxLayout(size_hint_y=None, height=dp(72), spacing=dp(4))
                if kind != "audio":
                    row.add_widget(AsyncImage(source="http://%s:%d/thumb?t=%s&uri=%s" % (ip, port, tok, quote(it["uri"], safe="")),
                                              size_hint_x=.3))
                row.add_widget(L(it.get("name", "")[:30], halign="right"))
                row.add_widget(B("اختيار", lambda it=it: (p.dismiss(), cb({"kind": kind, "src": "gallery", "uri": it["uri"],
                                                                          "name": it.get("name", "")})), GREEN, 48, 0.3))
                g.add_widget(row)
        threading.Thread(target=work, daemon=True).start()

    # ---- uploading local media to the Receiver over Wi-Fi
    def upload_file(self, path):
        self.wifi_bind(force=True)
        r = self.rinfo; name = os.path.basename(path)
        return transfer.upload_resumable(r["ip"], r["port"], r["token"], path,
            progress=lambda sent, total: self.toast_later("رفع %s: %d%%" % (name[:20], 100 * sent // max(total, 1))))

    def resolve_scenes(self, scenes, done, fail):
        out = json.loads(json.dumps(scenes)); cache = {}
        def local(sc):                       # everything in a scene that still has to be uploaded from this phone
            return ([(sc[k], k) for k in ("visual", "audio") if (sc.get(k) or {}).get("src") == "local"]
                    + [(z, "zone") for z in ZN.local_refs(sc)]
                    + [(l, "layer") for l in (sc.get("layers") or []) if isinstance(l, dict) and l.get("kind") == "image" and l.get("src") == "local"])
        if not any(local(sc) for sc in out): return done(out)
        if not self.rinfo:
            return fail("لرفع الوسائط: اتصل أولاً، وتأكد أن الجهازين على نفس شبكة الواي فاي")
        def run():
            try:
                for sc in out:
                    for m, k in local(sc):
                        if m["path"] not in cache: cache[m["path"]] = self.upload_file(m["path"])
                        if k == "zone":
                            m["src"] = "upload"; m["name"] = cache[m["path"]]; m["path"] = ""
                        elif k == "layer":
                            m["src"] = "upload"; m["file"] = cache[m["path"]]; m["path"] = ""
                        else:
                            sc[k] = {"kind": m["kind"], "src": "upload", "name": cache[m["path"]], "loop": bool(m.get("loop", True)), "fit": m.get("fit", "contain")}
                Clock.schedule_once(lambda dt: done(out), 0)
            except Exception as e:
                msg = "فشل الرفع: %s" % e
                Clock.schedule_once(lambda dt: fail(msg), 0)
        threading.Thread(target=run, daemon=True).start()

    def run_scene(self, scene):
        if not self.is_ready(): return self.toast("غير متصل بجهاز العرض")
        self.toast("جاري التجهيز...")
        self.resolve_scenes([scene], lambda r: self.send("apply_scene", r[0]), self.toast)

    def send_scene(self, scene, msg="سيتم استبدال المعروض على جهاز العرض. متابعة؟"):
        confirm(msg, lambda: self.run_scene(scene))

    # ---- scenes from saved items
    def scene_of(self, memo):
        if memo.get("scene"):
            sc = copy.deepcopy(memo["scene"])
        else:
            sc = self.sm.get_screen("text").scene()
            sc.pop("visual", None); sc.pop("audio", None)
        body = memo.get("body", "")
        old = sc["text"].get("msgs", [])
        sc["text"]["msgs"] = [l for l in body.splitlines() if l.strip()] if len(old) > 1 else [body]
        return sc

    def send_memo(self, it):
        self.send_scene(self.scene_of(it), "إرسال «%s» واعتماده؟" % it.get("name", ""))
    def send_page(self, it):
        confirm("إرسال «%s» واعتماده؟" % it.get("name", ""),
                lambda: self.send("apply_design", json.loads(it.get("body") or "{}")))
    def send_playlist(self, it):
        names = [n.strip() for n in it.get("items", "").splitlines() if n.strip()]
        memos = {m["name"]: m for m in self.store.d["memos"]}
        scenes = [self.scene_of(memos[n]) for n in names if n in memos]
        if not scenes: return self.toast("لا توجد مذكرات بهذه الأسماء")
        def go():
            if not self.is_ready(): return self.toast("غير متصل بجهاز العرض")
            self.toast("جاري التجهيز...")
            self.resolve_scenes(scenes, lambda r: self.send("apply_playlist",
                {"scenes": r, "secs": int(it.get("secs") or 10), "loop": True}), self.toast)
        confirm("إرسال قائمة التشغيل كاملة؟", go)
    def open_design(self, it):
        try: d = json.loads(it.get("body") or "{}")
        except Exception: self.toast("تصميم غير صالح"); return
        self.go("designer"); Clock.schedule_once(lambda *_: self.designer.load(d), 0.2)

    def check_schedule(self, dt):
        now = time.strftime("%Y-%m-%d %H:%M")
        for s in self.store.d["schedules"]:
            if s.get("when", "").strip() == now and s["id"] + now not in self.fired:
                self.fired.add(s["id"] + now)
                m = next((x for x in self.store.d["memos"] if x["name"] == s.get("memo")), None)
                if m: self.run_scene(self.scene_of(m)); self.store.log("جدولة: " + s["name"])

SenderApp().run()
