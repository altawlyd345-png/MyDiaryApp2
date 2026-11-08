import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import zones as Z

TEMPLATES = {"full": 1, "split-vertical": 2, "split-horizontal": 2, "three-columns": 3, "main-sidebar": 2, "grid-4": 4}

class Layouts(unittest.TestCase):
    def test_six_catalog_layouts_with_expected_zone_counts(self):
        self.assertEqual(sorted(Z.template_ids()), sorted(list(TEMPLATES) + [Z.CUSTOM]))
        for tid, n in TEMPLATES.items(): self.assertEqual(len(Z.template_zones(tid)), n, tid)
    def test_zones_tile_the_screen_without_overlap_or_gaps(self):
        for tid in TEMPLATES:
            zs = Z.template_zones(tid); area = 0
            for z in zs:
                self.assertTrue(0 <= z["x"] and 0 <= z["y"] and z["x"] + z["w"] <= 1.0001 and z["y"] + z["h"] <= 1.0001, tid)
                area += z["w"] * z["h"]
            self.assertAlmostEqual(area, 1.0, places=2, msg=tid)
            for i, a in enumerate(zs):
                for b in zs[i + 1:]:
                    ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]); oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
                    self.assertFalse(ox > 1e-3 and oy > 1e-3, "%s overlap %s/%s" % (tid, a["id"], b["id"]))
    def test_every_zone_has_an_arabic_name(self):
        for tid in TEMPLATES:
            for z in Z.template_zones(tid): self.assertNotEqual(Z.zone_name(z["id"]), z["id"], z["id"])
    def test_user_examples(self):
        v = {z["id"]: z for z in Z.template_zones("split-vertical")}            # video on the right, ad on the left
        self.assertEqual((v["right"]["x"], v["right"]["w"], v["left"]["x"]), (0.5, 0.5, 0.0))
        h = {z["id"]: z for z in Z.template_zones("split-horizontal")}
        self.assertGreater(h["top"]["y"], h["bottom"]["y"])
        self.assertEqual([z["id"] for z in Z.template_zones("three-columns")], ["left", "center", "right"])

class Content(unittest.TestCase):
    def test_set_content_keeps_geometry_and_id(self):
        zs = Z.set_content(Z.template_zones("split-vertical"), "right", kind="video", src="local", name="a.mp4", path="/s/a.mp4", x=0.9, w=0.01)
        r = Z.find(zs, "right"); self.assertEqual((r["kind"], r["x"], r["w"]), ("video", 0.5, 0.5))
        self.assertEqual(Z.find(zs, "left")["kind"], "empty")
    def test_media_without_source_becomes_empty(self):
        self.assertEqual(Z.normalize_zone({"id": "a", "kind": "image"})["kind"], "empty")
        self.assertEqual(Z.normalize_zone({"id": "a", "kind": "text", "text": "مرحبا"})["kind"], "text")
    def test_garbage_never_raises(self):
        for bad in (None, 5, "x", [1, None], {"id": 7, "x": "a", "w": float("nan"), "kind": "bomb", "color": "red", "size": -3, "loop": 0}):
            z = Z.normalize_zone(bad); self.assertIn(z["kind"], Z.KINDS); self.assertTrue(0 <= z["x"] <= 1 and 0 < z["w"] <= 1)
        self.assertEqual(Z.normalize_zones("nope"), []); self.assertEqual(len(Z.normalize_zones([{"id": str(i)} for i in range(30)])), Z.MAX_ZONES)
    def test_duplicate_ids_dropped(self):
        self.assertEqual(len(Z.normalize_zones([{"id": "a"}, {"id": "a"}, {"id": "b"}])), 2)
    def test_arabic_text_roundtrip(self):
        t = "مرحباً بكم في معرض WALIBRA ٢٠٢٦"
        z = Z.set_content(Z.template_zones("full"), "main", kind="text", text=t)[0]
        self.assertEqual(Z.normalize_zone(z)["text"], t); self.assertIn("نص", Z.summary(z))
    def test_summary_is_short_arabic(self):
        z = Z.normalize_zone({"id": "a", "kind": "video", "src": "local", "name": "x" * 90})
        self.assertTrue(Z.summary(z).startswith("فيديو")); self.assertLess(len(Z.summary(z)), 30)

class Commands(unittest.TestCase):
    def scene(self): return Z.zone_scene("split-vertical", Z.set_content(Z.template_zones("split-vertical"), "left", kind="image", src="upload", name="ad.png"))
    def test_zone_set_replaces_only_that_zone(self):
        sc = self.scene(); z = Z.valid_zone_command({"zone": {"id": "right", "kind": "video", "src": "upload", "name": "v.mp4", "x": 0, "w": 1}})
        self.assertTrue(Z.apply_zone(sc, z))
        self.assertEqual(Z.find(sc["zones"], "right")["kind"], "video"); self.assertEqual(Z.find(sc["zones"], "right")["x"], 0.5)   # geometry of the scene wins
        self.assertEqual(Z.find(sc["zones"], "left")["name"], "ad.png")                                                           # untouched
    def test_invalid_commands(self):
        for bad in (None, {}, {"zone": 5}, {"zone": {}}, {"zone": {"kind": "image"}}): self.assertIsNone(Z.valid_zone_command(bad))
        self.assertFalse(Z.apply_zone(self.scene(), Z.normalize_zone({"id": "ghost"}))); self.assertFalse(Z.apply_zone({"bg": "#000"}, Z.normalize_zone({"id": "left"})))
    def test_local_refs_only_for_local_media(self):
        zs = Z.set_content(Z.template_zones("three-columns"), "left", kind="image", src="local", path="/p/a.png", name="a.png")
        zs = Z.set_content(zs, "center", kind="video", src="gallery", uri="content://v", name="v.mp4")
        zs = Z.set_content(zs, "right", kind="text", text="x")
        self.assertEqual([z["id"] for z in Z.local_refs({"zones": zs})], ["left"])

def tiles(zs):
    """True when zones cover the screen exactly once (no gap, no overlap, inside the screen)."""
    area = sum(z["w"] * z["h"] for z in zs)
    for z in zs:
        if not (0 <= z["x"] and 0 <= z["y"] and z["x"] + z["w"] <= 1.0001 and z["y"] + z["h"] <= 1.0001): return False
    for i, a in enumerate(zs):
        for b in zs[i + 1:]:
            ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]); oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if ox > 1e-3 and oy > 1e-3: return False
    return abs(area - 1.0) < 0.01


class Resizing(unittest.TestCase):
    def test_every_ratio_template_tiles_the_screen_at_extremes(self):
        for tid, params in Z.PARAMS.items():
            for pick in (0, 1, 2):                           # min, max, default of every parameter
                r = {k: (lo, hi, d)[pick] for k, _l, lo, hi, d in params}
                self.assertTrue(tiles(Z.layout_zones(tid, r)), (tid, r))
    def test_ratios_are_clamped_and_garbage_safe(self):
        self.assertEqual(Z.clamp_ratios("split-vertical", {"a": 5})["a"], 0.8); self.assertEqual(Z.clamp_ratios("split-vertical", {"a": -1})["a"], 0.2)
        self.assertEqual(Z.clamp_ratios("split-vertical", {"a": "x"})["a"], 0.5); self.assertEqual(Z.clamp_ratios("full", {"a": 1}), {})
        r = Z.clamp_ratios("three-columns", {"a": 0.6, "b": 0.6}); self.assertGreaterEqual(1 - r["a"] - r["b"], 0.1499)
        self.assertTrue(tiles(Z.layout_zones("three-columns", {"a": 0.6, "b": 0.6})))
    def test_seventy_thirty_split(self):
        g = {z["id"]: z for z in Z.layout_zones("split-vertical", {"a": 0.7})}
        self.assertEqual((g["left"]["w"], g["right"]["x"], g["right"]["w"]), (0.7, 0.7, 0.3))
        h = {z["id"]: z for z in Z.layout_zones("split-horizontal", {"a": 0.3})}
        self.assertAlmostEqual(h["top"]["h"], 0.3); self.assertAlmostEqual(h["top"]["y"], 0.7); self.assertAlmostEqual(h["bottom"]["h"], 0.7)
    def test_infer_ratios_roundtrip(self):
        for tid, params in Z.PARAMS.items():
            r = {k: round((lo + hi) / 2, 4) for k, _l, lo, hi, _d in params}
            r = Z.clamp_ratios(tid, r)
            self.assertEqual(Z.infer_ratios(tid, Z.layout_zones(tid, r)), r, tid)
    def test_custom_grid_all_sizes(self):
        for c in (1, 2, 3):
            for r in (1, 2, 3):
                zs = Z.grid_zones(c, r); self.assertEqual(len(zs), c * r); self.assertTrue(tiles(zs), (c, r))
                labels = [Z.zone_label(z) for z in zs]; self.assertEqual(len(set(labels)), len(labels), (c, r, labels)); self.assertTrue(all(labels))
                self.assertEqual(Z.infer_grid(zs), (c, r))
        self.assertEqual(len(Z.grid_zones(9, 9)), 9); self.assertEqual(Z.zone_label(Z.grid_zones(1, 1)[0]), "الرئيسية")
    def test_contents_follow_the_zone_when_resizing_and_the_order_when_changing_layout(self):
        zs = Z.set_content(Z.layout_zones("split-vertical"), "right", kind="text", text="يمين")
        zs = Z.regeometry(zs, Z.layout_zones("split-vertical", {"a": 0.7}), by="id")
        self.assertEqual(Z.find(zs, "right")["text"], "يمين"); self.assertAlmostEqual(Z.find(zs, "right")["w"], 0.3)
        zs2 = Z.regeometry(zs, Z.layout_zones("three-columns"), by="index")
        self.assertEqual([z["kind"] for z in zs2], ["empty", "text", "empty"])      # second zone's content stays second
    def test_label_survives_content_changes(self):
        zs = Z.grid_zones(2, 2); lab = Z.zone_label(zs[1])
        zs = Z.set_content(zs, zs[1]["id"], kind="text", text="x"); self.assertEqual(Z.zone_label(zs[1]), lab)
    def test_layout_is_saved_with_the_scene(self):
        sc = Z.zone_scene("grid-4", Z.layout_zones("grid-4", {"a": .3, "b": .6}), layout={"ratios": {"a": .3, "b": .6}, "cols": 9, "rows": 0})
        self.assertEqual(sc["layout"]["ratios"], {"a": .3, "b": .6}); self.assertEqual((sc["layout"]["cols"], sc["layout"]["rows"]), (3, 1))


class Slideshow(unittest.TestCase):
    def items(self, n, src="local"): return [{"src": src, "name": "p%d.jpg" % i, "path": "/s/p%d.jpg" % i if src == "local" else "", "uri": "content://%d" % i if src == "gallery" else ""} for i in range(n)]
    def test_normalize(self):
        z = Z.normalize_zone({"id": "a", "kind": "slideshow", "items": self.items(3) + [{"src": "ftp"}, None, 5], "secs": 1, "trans": "spin"})
        self.assertEqual((z["kind"], len(z["items"]), z["secs"], z["trans"]), ("slideshow", 3, 2, "fade"))
        self.assertEqual(Z.normalize_zone({"id": "a", "kind": "slideshow", "items": []})["kind"], "empty")
        self.assertEqual(len(Z.normalize_zone({"id": "a", "kind": "slideshow", "items": self.items(40)})["items"]), Z.MAX_SLIDES)
        self.assertEqual(Z.normalize_zone({"id": "a", "kind": "slideshow", "items": self.items(2), "secs": 9999})["secs"], 120)
    def test_slides_are_uploaded_and_cached_like_other_media(self):
        zs = Z.set_content(Z.layout_zones("split-vertical"), "left", kind="slideshow", items=self.items(2))
        zs = Z.set_content(zs, "right", kind="slideshow", items=self.items(2, "gallery"))
        self.assertEqual(len(Z.local_refs({"zones": zs})), 2); self.assertEqual(len(Z.gallery_refs({"zones": zs})), 2)
        self.assertEqual(Z.summary(Z.find(zs, "left")), "عرض صور: 2 صور")
    def test_slide_items_never_leak_into_other_kinds(self):
        z = Z.set_content(Z.layout_zones("full"), "main", kind="text", text="x", items=self.items(2))[0]
        self.assertEqual(Z.local_refs({"zones": [z]}), [])


class TickerAndControl(unittest.TestCase):
    def test_ticker_normalize(self):
        z = Z.normalize_zone({"id": "t", "kind": "ticker", "text": "عاجل\nخبر", "speed": 99, "tdir": "up", "size": 9})
        self.assertEqual((z["kind"], z["speed"], z["tdir"], z["size"]), ("ticker", 10, "r2l", 0.5)); self.assertIn("شريط", Z.summary(z))
    def test_control_commands(self):
        self.assertEqual(Z.valid_zone_control({"zone": "right", "action": "volume", "value": 250}), ("right", "volume", 100))
        self.assertEqual(Z.valid_zone_control({"zone": "right", "action": "pause"}), ("right", "pause", 0))
        for a in Z.VIDEO_ACTIONS: self.assertIsNotNone(Z.valid_zone_control({"zone": "a", "action": a}))
        for bad in (None, {}, {"zone": "a"}, {"zone": "a", "action": "format"}, {"action": "pause"}, {"zone": "a", "action": "volume", "value": "x"}, 7):
            self.assertIsNone(Z.valid_zone_control(bad), bad)
    def test_volume_is_kept_and_clamped(self):
        self.assertEqual(Z.normalize_zone({"id": "v", "kind": "video", "src": "upload", "volume": 55})["volume"], 55)
        self.assertEqual(Z.normalize_zone({"id": "v", "volume": 900})["volume"], 100)


if __name__ == "__main__": unittest.main()
