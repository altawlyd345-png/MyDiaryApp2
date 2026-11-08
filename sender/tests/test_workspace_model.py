import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import workspace_model as W

SCREENS = {"designer": "مصمم الشاشة", "memos": "إدارة المذكرات"}

class Defaults(unittest.TestCase):
    def test_six_requested_cells_in_order(self):
        c = W.normalize(None)
        self.assertEqual(c["n"], 6)
        self.assertEqual([x["type"] for x in W.visible(c)],
                         ["group:text", "group:media", "group:image", "group:extra", "group:project", "group:more"])
        self.assertEqual(len(c["cells"]), W.MAX_CELLS)
    def test_every_default_type_is_valid(self):
        for t in W.DEFAULT_TYPES: self.assertTrue(W.is_valid(t), t)
    def test_all_group_settings_exist(self):
        for g, (label, items) in W.GROUPS.items():
            self.assertTrue(label)
            for k in items: self.assertIn(k, W.SETTINGS, k)
    def test_every_setting_belongs_to_a_group(self):
        used = {k for _, items in W.GROUPS.values() for k in items}
        self.assertEqual(used, set(W.SETTINGS))

class Normalize(unittest.TestCase):
    def test_garbage_never_raises(self):
        for bad in (None, 5, "x", [], {"n": "abc", "cells": 7}, {"n": 99, "cells": [None, 3, {"type": 5}]}):
            c = W.normalize(bad)
            self.assertTrue(W.MIN_CELLS <= c["n"] <= W.MAX_CELLS)
            self.assertEqual(len(c["cells"]), W.MAX_CELLS)
            for x in c["cells"]: self.assertTrue(W.is_valid(x["type"]) and x["name"])
    def test_count_is_clamped(self):
        self.assertEqual(W.normalize({"n": 1})["n"], 4)
        self.assertEqual(W.normalize({"n": 50})["n"], 10)
    def test_invalid_type_falls_back_to_default_for_that_slot(self):
        c = W.normalize({"n": 6, "cells": [{"type": "setting:nope", "name": "x"}]})
        self.assertEqual(c["cells"][0]["type"], "group:text")
    def test_long_and_blank_names(self):
        c = W.normalize({"n": 6, "cells": [{"type": "group:text", "name": "ا" * 80}, {"type": "group:media", "name": "   "}]})
        self.assertEqual(len(c["cells"][0]["name"]), W.NAME_MAX)
        self.assertEqual(c["cells"][1]["name"], "الفيديو والصوت")
    def test_unknown_screen_rejected_when_screens_known(self):
        self.assertFalse(W.is_valid("screen:ghost", SCREENS))
        self.assertTrue(W.is_valid("screen:designer", SCREENS))
        c = W.normalize({"n": 6, "cells": [{"type": "screen:ghost"}]}, SCREENS)
        self.assertEqual(c["cells"][0]["type"], "group:text")
    def test_roundtrip_is_stable(self):
        c = W.normalize(None); self.assertEqual(W.normalize(W.copy_config(c)), c)

class Editing(unittest.TestCase):
    def test_shrinking_keeps_hidden_cells(self):
        c = W.normalize(None); W.set_cell(c, 7, "action:clear", "مسح")
        W.set_count(c, 4); self.assertEqual(len(W.visible(c)), 4)
        W.set_count(c, 9); self.assertEqual(W.visible(c)[7]["type"], "action:clear")
    def test_pull_a_setting_into_a_cell(self):
        c = W.normalize(None)
        self.assertTrue(W.set_cell(c, 5, "setting:text.color"))
        self.assertEqual(c["cells"][5]["name"], "لون النص")
        self.assertEqual(W.panel_items("setting:text.color"), ["text.color"])
        self.assertEqual(W.panel_items("group:image")[:4], ["image.pick", "image.manage", "image.size", "image.pos"])
        for k in ("image.anim", "image.fit", "image.style", "image.live", "image.remove"): self.assertIn(k, W.panel_items("group:image"))
        self.assertEqual(W.panel_items("action:send"), [])
    def test_set_cell_rejects_bad_input(self):
        c = W.normalize(None)
        self.assertFalse(W.set_cell(c, 0, "setting:nope")); self.assertFalse(W.set_cell(c, 99, "group:text"))
        self.assertEqual(c["cells"][0]["type"], "group:text")
    def test_rename_and_move(self):
        c = W.normalize(None)
        W.rename_cell(c, 0, "  كتابة  "); self.assertEqual(c["cells"][0]["name"], "كتابة")
        W.rename_cell(c, 0, ""); self.assertEqual(c["cells"][0]["name"], "النصوص")
        self.assertTrue(W.move_cell(c, 0, 1)); self.assertEqual(c["cells"][1]["type"], "group:text")
        self.assertFalse(W.move_cell(c, 0, -1)); self.assertFalse(W.move_cell(c, 5, 1))
    def test_layout_rows(self):
        self.assertEqual(W.layout(4), (4, 1)); self.assertEqual(W.layout(5), (5, 1))
        self.assertEqual(W.layout(6), (3, 2)); self.assertEqual(W.layout(7), (4, 2))
        self.assertEqual(W.layout(10), (5, 2))
        for n in range(4, 11):
            cols, rows = W.layout(n); self.assertTrue(cols * rows >= n and rows <= 2)

if __name__ == "__main__":
    unittest.main()
