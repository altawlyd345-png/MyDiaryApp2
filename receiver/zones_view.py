"""Receiver: draws the zones of a split-screen scene.
Images, slideshows, text and tickers are Kivy widgets (each zone clips its own content); every video zone is its own
native player (see ZoneVideo.java), so several videos can play at once and one zone can change without touching the others."""
import os

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.stencilview import StencilView
from kivy.utils import get_color_from_hex as H

import zones as Z
from protocol import shape


def shape_lines(text):
    """Arabic shaping line by line (bidi on a multi-line string can reorder lines)."""
    return "\n".join(shape(line) for line in str(text).split("\n"))


def make_image(path, fit):
    try:
        return Image(source=path, fit_mode=fit, size_hint=(1, 1), nocache=True)
    except TypeError:
        return Image(source=path, allow_stretch=True, keep_ratio=fit != "fill", size_hint=(1, 1), nocache=True)


class ZoneBox(StencilView, FloatLayout):
    """One zone. StencilView clips everything to the zone rectangle (a ticker or a sliding image never leaks out)."""
    def __init__(self, z, view, **kw):
        super().__init__(size_hint=(z["w"], z["h"]), pos_hint={"x": z["x"], "y": z["y"]}, **kw)
        self.view = view
        with self.canvas.before:
            self._c = Color(*H(z["bg"]))
            self._r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._u, size=self._u)
        self._tick = None; self._slides = []; self._cur = None; self._idx = 0; self._lbl = None; self._cbs = []
        self.z = z
        self.set(z)

    def _u(self, *a):
        self._r.pos, self._r.size = self.pos, self.size

    # ---- life cycle
    def halt(self):
        """Stop timers and animations of this zone (not the native video: ZonesView does that)."""
        if self._tick is not None:
            self._tick.cancel(); self._tick = None
        for w in list(self.children):
            Animation.cancel_all(w)
        for name, cb in self._cbs:                      # drop the size/height bindings made for the old content
            self.unbind(**{name: cb})
        self._cbs = []; self._slides = []; self._cur = None; self._lbl = None

    def set(self, z):
        """Show a (normalized) zone. Replaces whatever this box showed before."""
        self.halt()
        self.z = z
        self.clear_widgets()
        kind = z["kind"]
        self._c.rgba = H(z["bg"]) if kind in ("text", "ticker", "empty") else (0, 0, 0, 1)
        if kind == "image":
            path = self.view.resolve(z)
            if path:
                self.add_widget(make_image(path, z["fit"]))
        elif kind == "slideshow":
            self._start_slides(z)
        elif kind == "text" and z["text"].strip():
            self._text(z)
        elif kind == "ticker" and z["text"].strip():
            self._start_ticker(z)
        # video zones draw nothing here: the native player is placed over this rectangle
        self.view.video(z)

    # ---- text
    def _label(self, z, text, **kw):
        lbl = Label(text=shape_lines(text), color=H(z["color"]), **self.view.font_kw, **kw)
        size = z["size"]
        cb = lambda i, v: setattr(lbl, "font_size", max(8.0, size * v))
        self.bind(height=cb); self._cbs.append(("height", cb))
        lbl.font_size = max(8.0, size * max(self.height, 1))
        return lbl

    def _text(self, z):
        lbl = self._label(z, z["text"], halign=z["align"], valign="middle", size_hint=(1, 1))
        lbl.bind(size=lambda i, v: setattr(i, "text_size", (v[0] * 0.92, v[1] * 0.92)))
        self.add_widget(lbl)

    # ---- ticker: one line scrolling across the zone
    def _start_ticker(self, z):
        text = "   •   ".join(t.strip() for t in z["text"].split("\n") if t.strip())
        lbl = self._label(z, text, size_hint=(None, None), halign="left", valign="middle")
        lbl.texture_update(); lbl.size = lbl.texture_size
        self.add_widget(lbl); self._lbl = lbl
        self._ticker_place(lbl, z, start=True)
        fresh = [True]                                  # the first real layout of the zone re-places the start position
        def on_size(*a):
            self._ticker_place(lbl, z, start=fresh[0]); fresh[0] = False
        self.bind(size=on_size); self._cbs.append(("size", on_size))
        self._tick = Clock.schedule_interval(lambda dt: self._ticker_step(dt, z), 1 / 30.0)

    def _ticker_place(self, lbl, z, start):
        lbl.texture_update(); lbl.size = lbl.texture_size
        lbl.y = self.y + (self.height - lbl.height) / 2
        if start:
            lbl.x = self.right if z["tdir"] == "r2l" else self.x - lbl.width

    def _ticker_step(self, dt, z):
        lbl = self._lbl
        if lbl is None:
            return
        step = max(30.0, self.width * 0.05 * z["speed"]) * dt
        lbl.y = self.y + (self.height - lbl.height) / 2
        if z["tdir"] == "r2l":
            lbl.x -= step
            if lbl.right < self.x:
                lbl.x = self.right
        else:
            lbl.x += step
            if lbl.x > self.right:
                lbl.x = self.x - lbl.width

    # ---- slideshow: several images in turn
    def _start_slides(self, z):
        self._slides = [p for p in (self.view.resolve(i) for i in z["items"]) if p]
        self._idx = 0
        if not self._slides:
            return
        self._show(self._slides[0], first=True)
        if len(self._slides) > 1:
            self._tick = Clock.schedule_interval(lambda dt: self._next(), max(2, z["secs"]))

    def _next(self):
        if not self._slides:
            return
        self._idx = (self._idx + 1) % len(self._slides)
        self._show(self._slides[self._idx], first=False)

    def _show(self, path, first):
        z = self.z; old = self._cur
        img = make_image(path, z["fit"])
        trans = "none" if first else z["trans"]
        self.add_widget(img); self._cur = img
        if old is None or trans == "none":
            if old is not None:
                self.remove_widget(old)
            return
        dur = 0.6
        if trans == "fade":
            img.opacity = 0
            Animation(opacity=1, duration=dur).start(img)
        else:                                   # slide: manual positions, both images move together
            sign = 1 if trans == "slide_left" else -1
            for w in (img, old):
                w.size_hint = (None, None); w.size = self.size
            img.pos = (self.x + sign * self.width, self.y); old.pos = (self.x, self.y)
            Animation(x=self.x, duration=dur, t="out_quad").start(img)
            Animation(x=self.x - sign * self.width, duration=dur, t="out_quad").start(old)
        Clock.schedule_once(lambda dt, o=old: self.remove_widget(o) if o.parent is self else None, dur + 0.1)


class ZonesView(FloatLayout):
    """All zones of the current scene. `app` provides media_path(item) and zone_video(zone, on)."""
    def __init__(self, app, font="", **kw):
        super().__init__(**kw)
        self.app = app
        self.font_kw = {"font_name": font} if font else {}
        self.boxes = {}

    def resolve(self, z):
        try:
            p = self.app.media_path(z) if z.get("src") in ("upload", "gallery") else None
        except Exception:
            p = None
        return p if p and os.path.isfile(p) else None

    def video(self, z):
        try:
            self.app.zone_video(z, z["kind"] == "video")
        except Exception:
            pass

    def build(self, zones):
        self.stop()
        self.clear_widgets()
        self.boxes = {}
        for z in Z.normalize_zones(zones):
            box = ZoneBox(z, self)
            self.boxes[z["id"]] = box
            self.add_widget(box)

    def update(self, zone):
        """Replace the content of ONE zone; the other zones (and their videos) keep running."""
        z = Z.normalize_zone(zone, zone.get("id", "z"))
        box = self.boxes.get(z["id"])
        if box is None:
            return False
        box.set(z)
        return True

    def stop(self):
        for zid, box in list(self.boxes.items()):
            try:
                box.halt()
            except Exception:
                pass
            try:
                self.app.zone_video({"id": zid, "kind": "empty"}, False)
            except Exception:
                pass
