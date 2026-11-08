"""Workspace cell layout (pure data, no Kivy).

The new main screen = live preview on top + a bottom bar of N cells (4..10).
Each cell has a type and a name:
    group:<g>      opens a panel with several settings (text / media / image / extra / project / more)
    setting:<key>  opens a panel with ONE setting (this is how a setting is "pulled out" into its own cell)
    action:<key>   runs immediately (send, hide, clear, ...)
    screen:<key>   opens one of the app's existing screens
"""
import copy
import math

MIN_CELLS, MAX_CELLS, DEFAULT_CELLS = 4, 10, 6
NAME_MAX = 20

SETTINGS = {
    "text.entry": "نص العرض", "text.color": "لون النص", "text.bg": "لون خلفية النص", "text.size": "حجم النص",
    "text.align": "المحاذاة", "text.font": "نوع الخط", "text.anim": "طريقة العرض والحركة",
    "text.pos": "الموضع والشفافية", "text.live": "إخفاء / إظهار النص",
    "media.video": "اختيار فيديو", "media.audio": "اختيار صوت", "media.control": "تشغيل وإيقاف",
    "media.volume": "مستوى الصوت", "media.loop": "التكرار",
    "media.sender_list": "وسائط هذا الجوال", "media.receiver_list": "وسائط جهاز العرض",
    "image.pick": "إدراج صورة", "image.manage": "الصور المدرجة", "image.size": "حجم الصورة", "image.pos": "مكان الصورة",
    "image.anim": "كيفية ظهور الصورة", "image.fit": "طريقة عرض الصورة", "image.style": "الشفافية والتدوير",
    "image.live": "إخفاء / إظهار الصورة", "image.remove": "حذف الصورة",
    "extra.manage": "النصوص الإضافية", "extra.entry": "نص الإضافي المحدد", "extra.color": "لون الإضافي",
    "extra.size": "حجم الإضافي", "extra.pos": "موضع الإضافي",
    "project.open": "فتح مشهد محفوظ", "project.save": "حفظ المشهد", "project.templates": "القوالب الجاهزة",
    "project.projects": "المشاريع", "project.new": "مشهد جديد",
    "more.content": "مدير المحتوى المتقدم", "more.texts": "إدارة النصوص",
    "more.design": "استديو التصميم", "more.emergency": "وضع الطوارئ", "more.split": "تقسيم الشاشة",
    "more.customize": "تخصيص الخانات", "more.all": "كل الميزات",
}

GROUPS = {
    "text": ("النصوص", ["text.entry", "text.color", "text.bg", "text.size", "text.align", "text.font",
                        "text.anim", "text.pos", "text.live"]),
    "media": ("الفيديو والصوت", ["media.video", "media.audio", "media.control", "media.volume", "media.loop",
                                 "media.sender_list", "media.receiver_list"]),
    "image": ("الصور", ["image.pick", "image.manage", "image.size", "image.pos", "image.anim", "image.fit", "image.style",
                        "image.live", "image.remove"]),
    "extra": ("نص إضافي", ["extra.manage", "extra.entry", "extra.color", "extra.size", "extra.pos"]),
    "project": ("مشروع جاهز", ["project.open", "project.save", "project.new", "project.templates", "project.projects"]),
    "more": ("المزيد", ["more.content", "more.texts", "more.design", "more.emergency", "more.split",
                          "more.customize", "more.all"]),
}

ACTIONS = {
    "send": "إرسال واعتماد وعرض", "hide": "إخفاء المحتوى", "restore": "استعادة آخر عرض",
    "clear": "مسح الشاشة", "media_pause": "إيقاف مؤقت", "media_resume": "استئناف التشغيل",
    "media_restart": "إعادة من البداية", "replay": "إعادة حركة المعاينة",
}

# first six = the cells the user asked for; the rest fill the extra slots until he changes them
DEFAULT_TYPES = ["group:text", "group:media", "group:image", "group:extra", "group:project", "group:more",
                 "action:send", "action:hide", "action:restore", "action:clear"]


def type_label(t, screens=None):
    """Arabic default label for a cell type, or '' if the type is not valid."""
    if not isinstance(t, str) or ":" not in t:
        return ""
    kind, key = t.split(":", 1)
    if kind == "group":
        return GROUPS[key][0] if key in GROUPS else ""
    if kind == "setting":
        return SETTINGS.get(key, "")
    if kind == "action":
        return ACTIONS.get(key, "")
    if kind == "screen":
        if not key:
            return ""
        if screens is None:
            return key
        return screens.get(key, "")
    return ""


def is_valid(t, screens=None):
    return bool(type_label(t, screens))


def panel_items(t):
    """Setting keys a cell opens in its panel ([] for actions and screens)."""
    if not isinstance(t, str) or ":" not in t:
        return []
    kind, key = t.split(":", 1)
    if kind == "group" and key in GROUPS:
        return list(GROUPS[key][1])
    if kind == "setting" and key in SETTINGS:
        return [key]
    return []


def _clean_name(name, fallback):
    name = " ".join(str(name or "").split())[:NAME_MAX]
    return name or fallback


def default_cell(index, screens=None):
    t = DEFAULT_TYPES[index % len(DEFAULT_TYPES)]
    return {"type": t, "name": _clean_name(type_label(t, screens), t)}


def default_config():
    return {"n": DEFAULT_CELLS, "cells": [default_cell(i) for i in range(MAX_CELLS)]}


def normalize(cfg, screens=None):
    """Always returns a usable config: n clamped, MAX_CELLS cells, valid types, non-empty names.
    Hidden cells (index >= n) are kept so that raising n again brings the old cells back."""
    cfg = cfg if isinstance(cfg, dict) else {}
    try:
        n = int(cfg.get("n", DEFAULT_CELLS))
    except (TypeError, ValueError):
        n = DEFAULT_CELLS
    n = max(MIN_CELLS, min(MAX_CELLS, n))
    raw = cfg.get("cells") if isinstance(cfg.get("cells"), list) else []
    cells = []
    for i in range(MAX_CELLS):
        c = raw[i] if i < len(raw) and isinstance(raw[i], dict) else {}
        t = c.get("type")
        if not is_valid(t, screens):
            c = default_cell(i, screens)
        else:
            c = {"type": t, "name": _clean_name(c.get("name"), type_label(t, screens))}
        cells.append(c)
    return {"n": n, "cells": cells}


def visible(cfg):
    return cfg["cells"][:cfg["n"]]


def set_count(cfg, n):
    cfg["n"] = max(MIN_CELLS, min(MAX_CELLS, int(n)))
    return cfg


def set_cell(cfg, i, t, name=None, screens=None):
    """Assign a type to cell i. The name defaults to the type's label."""
    if not (0 <= i < MAX_CELLS) or not is_valid(t, screens):
        return False
    label = _clean_name(type_label(t, screens), t)
    cfg["cells"][i] = {"type": t, "name": _clean_name(name, label) if name else label}
    return True


def rename_cell(cfg, i, name):
    if not (0 <= i < MAX_CELLS):
        return False
    t = cfg["cells"][i]["type"]
    cfg["cells"][i]["name"] = _clean_name(name, type_label(t) or t)
    return True


def move_cell(cfg, i, delta):
    """Swap cell i with its neighbour (within the visible cells)."""
    j = i + delta
    n = cfg["n"]
    if not (0 <= i < n and 0 <= j < n):
        return False
    cfg["cells"][i], cfg["cells"][j] = cfg["cells"][j], cfg["cells"][i]
    return True


def layout(n):
    """(cols, rows) for the bottom bar: one row up to 5 cells, otherwise two balanced rows."""
    n = max(MIN_CELLS, min(MAX_CELLS, int(n)))
    cols = n if n <= 5 else math.ceil(n / 2)
    return cols, math.ceil(n / cols)


def copy_config(cfg):
    return copy.deepcopy(cfg)
