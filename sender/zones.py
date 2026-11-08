"""WALIBRA split screen: independent zones, each with its own content (pure Python, no Kivy).

A zone scene is a normal scene plus a "zones" list. Coordinates are fractions of the screen,
x,y = lower-left corner, w,h = size.  A zone shows ONE thing:
    image | video | text | slideshow (several images in turn) | ticker (scrolling text) | nothing.
Media source:  local   - a file on the Sender (uploaded to the Receiver before sending)
               gallery - a file that already lives on the Receiver (content:// URI)
               upload  - a file already uploaded to the Receiver (name inside its media folder)
"""
import copy

import templates as TPL

KINDS = ("empty", "image", "video", "text", "slideshow", "ticker")
SRCS = ("local", "gallery", "upload")
FITS = ("contain", "cover", "fill", "scale-down")
ALIGNS = ("left", "center", "right")
TRANS = ("none", "fade", "slide_left", "slide_right")
TDIRS = ("r2l", "l2r")
VIDEO_ACTIONS = ("pause", "resume", "restart", "volume", "mute", "unmute")
MAX_ZONES = 9
MAX_SLIDES = 12
CUSTOM = "custom-grid"

KIND_NAMES = {"empty": "فارغة", "image": "صورة", "video": "فيديو", "text": "نص", "slideshow": "عرض صور", "ticker": "شريط أخبار"}
ZONE_NAMES = {
    "main": "الرئيسية", "left": "اليسار", "right": "اليمين", "top": "الأعلى", "bottom": "الأسفل", "center": "الوسط",
    "sidebar": "الشريط الجانبي", "top-left": "أعلى اليسار", "top-right": "أعلى اليمين",
    "bottom-left": "أسفل اليسار", "bottom-right": "أسفل اليمين",
}
EMPTY = {"kind": "empty", "src": "", "name": "", "path": "", "uri": "", "fit": "contain", "loop": True, "mute": False,
         "volume": 100, "text": "", "color": "#FFFFFF", "bg": "#000000", "size": 0.12, "align": "center",
         "items": [], "secs": 5, "trans": "fade", "speed": 5, "tdir": "r2l", "label": ""}
CONTENT_KEYS = tuple(k for k in EMPTY if k != "label")

# resizable layouts: (key, Arabic label, min, max, default). Meaning is documented in layout_zones().
PARAMS = {
    "split-vertical": [("a", "عرض منطقة اليسار", 0.2, 0.8, 0.5)],
    "split-horizontal": [("a", "ارتفاع المنطقة العلوية", 0.2, 0.8, 0.5)],
    "three-columns": [("a", "عرض العمود الأول", 0.15, 0.6, 1 / 3), ("b", "عرض العمود الثاني", 0.15, 0.6, 1 / 3)],
    "main-sidebar": [("a", "عرض المنطقة الرئيسية", 0.4, 0.85, 0.72)],
    "grid-4": [("a", "عرض العمودين الأيسر", 0.2, 0.8, 0.5), ("b", "ارتفاع الصفين العلويين", 0.2, 0.8, 0.5)],
}
GRID_MIN, GRID_MAX = 1, 3


def zone_name(zid):
    return ZONE_NAMES.get(zid, str(zid))


def zone_label(z):
    """Name shown to the user: the zone's own label (custom grids) or the standard name of its id."""
    return (z.get("label") or "").strip() or zone_name(z.get("id", ""))


def _num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    if v != v:                       # NaN
        return default
    return max(lo, min(hi, v))


def _choice(v, allowed, default):
    return v if v in allowed else default


def _color(v, default):
    s = str(v or "")
    if len(s) == 7 and s[0] == "#":
        try:
            int(s[1:], 16)
            return s.upper()
        except ValueError:
            pass
    return default


def _item(it):
    """One slide of a slideshow, or None when it can never be shown."""
    it = it if isinstance(it, dict) else {}
    src = _choice(it.get("src"), SRCS, "")
    if not src:
        return None
    return {"src": src, "name": str(it.get("name", ""))[:200], "path": str(it.get("path", ""))[:1000],
            "uri": str(it.get("uri", ""))[:1000], "kind": "image"}


def normalize_zone(z, fallback_id="z"):
    """Clean, fully-defaulted copy of one zone. Never raises."""
    z = z if isinstance(z, dict) else {}
    out = copy.deepcopy(EMPTY)
    out["id"] = str(z.get("id") or fallback_id)[:24]
    x = _num(z.get("x"), 0.0, 1.0, 0.0); y = _num(z.get("y"), 0.0, 1.0, 0.0)
    out["x"], out["y"] = round(x, 4), round(y, 4)
    out["w"] = round(_num(z.get("w"), 0.02, 1.0 - x if x < 0.98 else 0.02, 1.0 - x if x < 1 else 0.02), 4)
    out["h"] = round(_num(z.get("h"), 0.02, 1.0 - y if y < 0.98 else 0.02, 1.0 - y if y < 1 else 0.02), 4)
    out["kind"] = _choice(z.get("kind"), KINDS, "empty")
    out["src"] = _choice(z.get("src"), SRCS, "")
    out["name"] = str(z.get("name", ""))[:200]
    out["path"] = str(z.get("path", ""))[:1000]
    out["uri"] = str(z.get("uri", ""))[:1000]
    out["fit"] = _choice(z.get("fit"), FITS, "contain")
    out["loop"] = bool(z.get("loop", True)); out["mute"] = bool(z.get("mute", False))
    out["volume"] = int(_num(z.get("volume"), 0, 100, 100))
    out["text"] = str(z.get("text", ""))[:1000]
    out["color"] = _color(z.get("color"), "#FFFFFF"); out["bg"] = _color(z.get("bg"), "#000000")
    out["size"] = _num(z.get("size"), 0.02, 0.5, 0.12)
    out["align"] = _choice(z.get("align"), ALIGNS, "center")
    items = [_item(i) for i in (z.get("items") if isinstance(z.get("items"), (list, tuple)) else [])]
    out["items"] = [i for i in items if i][:MAX_SLIDES]
    out["secs"] = int(_num(z.get("secs"), 2, 120, 5)); out["trans"] = _choice(z.get("trans"), TRANS, "fade")
    out["speed"] = int(_num(z.get("speed"), 1, 10, 5)); out["tdir"] = _choice(z.get("tdir"), TDIRS, "r2l")
    out["label"] = " ".join(str(z.get("label", "")).split())[:30]
    if out["kind"] in ("image", "video") and not out["src"]:
        out["kind"] = "empty"                            # media without a source can never be shown
    if out["kind"] == "slideshow" and not out["items"]:
        out["kind"] = "empty"
    return out


def normalize_zones(zs):
    """List of clean zones: max MAX_ZONES, unique ids."""
    out, seen = [], set()
    for i, z in enumerate(zs if isinstance(zs, (list, tuple)) else []):
        n = normalize_zone(z, "z%d" % (i + 1))
        if n["id"] in seen:
            continue
        seen.add(n["id"]); out.append(n)
        if len(out) >= MAX_ZONES:
            break
    return out


# ---------------------------------------------------------------- layouts (templates + resizing + custom grid)
def template_ids():
    """Catalog templates plus the custom grid."""
    return [t["id"] for t in TPL.load_templates()] + [CUSTOM]


def params_for(template_id):
    return PARAMS.get(template_id, [])


def default_ratios(template_id):
    return {k: d for k, _l, _lo, _hi, d in params_for(template_id)}


def clamp_ratios(template_id, ratios):
    """Ratios limited to each parameter's range; for three columns the last column keeps at least 15%."""
    ratios = ratios if isinstance(ratios, dict) else {}
    out = {k: _num(ratios.get(k), lo, hi, d) for k, _l, lo, hi, d in params_for(template_id)}
    if template_id == "three-columns":
        out["b"] = min(out["b"], 1.0 - out["a"] - 0.15)
        out["b"] = max(out["b"], 0.15)
    return {k: round(v, 4) for k, v in out.items()}


def _grid_label(r, c, rows, cols):
    if rows == 3 and cols == 3 and r == 1 and c == 1:
        return "المنتصف"
    rn = {1: [""], 2: ["أعلى", "أسفل"], 3: ["أعلى", "وسط", "أسفل"]}[rows][r]
    cn = {1: [""], 2: ["اليسار", "اليمين"], 3: ["اليسار", "الوسط", "اليمين"]}[cols][c]
    return (rn + " " + cn).strip() or "الرئيسية"


def grid_zones(cols, rows):
    cols = int(_num(cols, GRID_MIN, GRID_MAX, 2)); rows = int(_num(rows, GRID_MIN, GRID_MAX, 2))
    zs = []
    for r in range(rows):
        for c in range(cols):
            zs.append({"id": "r%dc%d" % (r + 1, c + 1), "x": c / cols, "y": 1 - (r + 1) / rows, "w": 1 / cols, "h": 1 / rows,
                       "label": _grid_label(r, c, rows, cols)})
    return normalize_zones(zs)


def layout_zones(template_id, ratios=None, cols=3, rows=2):
    """Empty zones for a layout. Ratios (see PARAMS):
       split-vertical a=left width | split-horizontal a=top height | three-columns a,b=first/second column width |
       main-sidebar a=main width   | grid-4 a=left column width, b=top row height | custom-grid uses cols x rows."""
    if template_id == CUSTOM:
        return grid_zones(cols, rows)
    zs = template_zones_catalog(template_id)
    r = clamp_ratios(template_id, ratios if ratios is not None else default_ratios(template_id))
    g = {z["id"]: z for z in zs}
    if template_id == "split-vertical":
        g["left"].update(x=0, w=r["a"]); g["right"].update(x=r["a"], w=1 - r["a"])
    elif template_id == "split-horizontal":
        g["top"].update(y=1 - r["a"], h=r["a"]); g["bottom"].update(y=0, h=1 - r["a"])
    elif template_id == "three-columns":
        g["left"].update(x=0, w=r["a"]); g["center"].update(x=r["a"], w=r["b"]); g["right"].update(x=r["a"] + r["b"], w=1 - r["a"] - r["b"])
    elif template_id == "main-sidebar":
        g["main"].update(x=0, w=r["a"]); g["sidebar"].update(x=r["a"], w=1 - r["a"])
    elif template_id == "grid-4":
        a, b = r["a"], r["b"]
        g["top-left"].update(x=0, y=1 - b, w=a, h=b); g["top-right"].update(x=a, y=1 - b, w=1 - a, h=b)
        g["bottom-left"].update(x=0, y=0, w=a, h=1 - b); g["bottom-right"].update(x=a, y=0, w=1 - a, h=1 - b)
    return normalize_zones(zs)


def template_zones_catalog(template_id):
    return normalize_zones(TPL.template_scene(template_id)["zones"])


def template_zones(template_id):
    """Empty zones laid out by a template with default sizes (raises KeyError for an unknown template)."""
    if template_id == CUSTOM:
        return grid_zones(3, 2)
    return layout_zones(template_id)


def infer_ratios(template_id, zones):
    """Resizing parameters read back from stored zone geometry (used when opening a saved layout)."""
    g = {z.get("id"): z for z in zones if isinstance(z, dict)}
    try:
        if template_id == "split-vertical": return clamp_ratios(template_id, {"a": g["left"]["w"]})
        if template_id == "split-horizontal": return clamp_ratios(template_id, {"a": g["top"]["h"]})
        if template_id == "three-columns": return clamp_ratios(template_id, {"a": g["left"]["w"], "b": g["center"]["w"]})
        if template_id == "main-sidebar": return clamp_ratios(template_id, {"a": g["main"]["w"]})
        if template_id == "grid-4": return clamp_ratios(template_id, {"a": g["top-left"]["w"], "b": g["top-left"]["h"]})
    except (KeyError, TypeError):
        pass
    return default_ratios(template_id)


def infer_grid(zones):
    """(cols, rows) of a saved custom grid from its zone ids."""
    cols = rows = 1
    for z in zones:
        zid = z.get("id", "") if isinstance(z, dict) else ""
        if len(zid) == 4 and zid[0] == "r" and zid[2] == "c" and zid[1].isdigit() and zid[3].isdigit():
            rows = max(rows, int(zid[1])); cols = max(cols, int(zid[3]))
    return min(cols, GRID_MAX), min(rows, GRID_MAX)


def regeometry(old, new, by="id"):
    """New layout `new` carrying the contents of `old`.
    by="id": zones with the same id keep their content (resizing); by="index": contents move in order (changing layout)."""
    by_id = {z["id"]: z for z in old}
    out = []
    for i, nz in enumerate(new):
        src = by_id.get(nz["id"]) if by == "id" else (old[i] if i < len(old) else None)
        z = copy.deepcopy(nz)
        if src is not None:
            for k in CONTENT_KEYS:
                z[k] = copy.deepcopy(src[k])
        out.append(normalize_zone(z, nz["id"]))
    return out


def geometry_sig(zones):
    return [(z["id"], z["x"], z["y"], z["w"], z["h"]) for z in zones]


def zone_scene(template_id, zones, bg="#000000", layout=None):
    sc = {"bg": _color(bg, "#000000"), "template_id": str(template_id)[:40], "zones": normalize_zones(zones)}
    if isinstance(layout, dict):
        sc["layout"] = {"ratios": layout.get("ratios") if isinstance(layout.get("ratios"), dict) else {},
                        "cols": int(_num(layout.get("cols"), GRID_MIN, GRID_MAX, 3)), "rows": int(_num(layout.get("rows"), GRID_MIN, GRID_MAX, 2))}
    return sc


def find(zones, zid):
    return next((z for z in zones if z.get("id") == zid), None)


def set_content(zones, zid, **content):
    """New zones list where zone `zid` gets `content` (geometry, id and label are never changed)."""
    out = []
    for z in zones:
        if z.get("id") == zid:
            keep = {k: z[k] for k in ("id", "x", "y", "w", "h", "label") if k in z}
            base = copy.deepcopy(EMPTY); base.update(content); base.update(keep)
            z = normalize_zone(base, zid)
        out.append(z)
    return out


def clear_zone(zones, zid):
    return set_content(zones, zid)


def media_zone(z):
    return z.get("kind") in ("image", "video") and bool(z.get("src"))


def local_refs(sc):
    """Dicts of a zone scene whose media must be uploaded from the Sender first (zones and slides)."""
    out = []
    for z in (sc.get("zones") or []):
        if not isinstance(z, dict):
            continue
        if media_zone(z) and z.get("src") == "local":
            out.append(z)
        if z.get("kind") == "slideshow":
            out += [i for i in (z.get("items") or []) if isinstance(i, dict) and i.get("src") == "local"]
    return out


def gallery_refs(sc):
    """Receiver-gallery IMAGES that must be copied into the Receiver cache (Kivy needs a file path)."""
    out = []
    for z in (sc.get("zones") or []):
        if not isinstance(z, dict):
            continue
        if z.get("kind") == "image" and z.get("src") == "gallery":
            out.append(z)
        if z.get("kind") == "slideshow":
            out += [i for i in (z.get("items") or []) if isinstance(i, dict) and i.get("src") == "gallery"]
    return out


def valid_zone_command(d):
    """Receiver side: payload of a "zone_set" command -> normalized zone, or None."""
    z = d.get("zone") if isinstance(d, dict) else None
    if not isinstance(z, dict) or not z.get("id"):
        return None
    return normalize_zone(z, str(z["id"]))


def valid_zone_control(d):
    """Receiver side: payload of a "zone_ctl" command -> (zone_id, action, value) or None."""
    if not isinstance(d, dict) or not d.get("zone"):
        return None
    action = d.get("action")
    if action not in VIDEO_ACTIONS:
        return None
    try:
        value = max(0, min(100, int(d.get("value", 0) or 0)))
    except (TypeError, ValueError):
        return None
    return str(d["zone"])[:24], action, value


def apply_zone(scene, zone):
    """Replace one zone's content inside a zone scene (geometry of the existing zone wins). Returns True if applied."""
    zs = scene.get("zones") if isinstance(scene, dict) else None
    if not isinstance(zs, list):
        return False
    for i, old in enumerate(zs):
        if isinstance(old, dict) and old.get("id") == zone["id"]:
            new = dict(zone)
            for k in ("x", "y", "w", "h", "label"):
                new[k] = old.get(k, zone.get(k, ""))
            zs[i] = normalize_zone(new, zone["id"])
            return True
    return False


def summary(z):
    """Short Arabic description of what a zone shows."""
    k = z.get("kind", "empty")
    if k == "empty":
        return KIND_NAMES["empty"]
    if k in ("text", "ticker"):
        t = " ".join(str(z.get("text", "")).split())
        return "%s: %s" % (KIND_NAMES[k], t[:18] or "…")
    if k == "slideshow":
        return "%s: %d صور" % (KIND_NAMES[k], len(z.get("items") or []))
    return "%s: %s" % (KIND_NAMES[k], str(z.get("name", ""))[:18] or "…")
