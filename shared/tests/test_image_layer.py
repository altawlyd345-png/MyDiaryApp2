import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio as S


class ImageLayer(unittest.TestCase):
    def test_defaults_and_clean_fields(self):
        l = S.normalize_layer({"kind": "image", "src": "local", "file": "a.jpg", "path": "/x/a.jpg", "fit": "cover", "w": 0.3, "h": 0.2, "x": 0.1, "y": 0.6})
        self.assertEqual((l["kind"], l["src"], l["file"], l["fit"]), ("image", "local", "a.jpg", "cover"))
        self.assertEqual((l["x"], l["y"], l["w"], l["h"]), (0.1, 0.6, 0.3, 0.2))
        d = S.normalize_layer({"kind": "image"})
        self.assertEqual((d["w"], d["h"], d["fit"], d["src"]), (0.5, 0.5, "contain", ""))
    def test_garbage_image_never_raises(self):
        l = S.normalize_layer({"kind": "image", "src": "ftp", "fit": "stretch", "file": 5, "path": None, "w": "x", "anim_in": "spin"})
        self.assertEqual((l["src"], l["fit"], l["anim_in"]), ("", "contain", "none"))
        self.assertTrue(0.02 <= l["w"] <= 1)
    def test_new_slide_effects_allowed(self):
        for a in ("slide_up", "slide_down"):
            self.assertEqual(S.normalize_layer({"kind": "image", "anim_in": a})["anim_in"], a)
            self.assertEqual(S.normalize_layer({"kind": "image", "anim_out": a})["anim_out"], a)
    def test_scene_roundtrip_keeps_image_layers(self):
        sc = S.normalize_scene({"layers": [{"id": "i1", "kind": "image", "src": "upload", "file": "u.png"}, {"id": "t", "kind": "text", "text": "x"}]})
        self.assertEqual([l["kind"] for l in sc["layers"]], ["image", "text"]); self.assertEqual(S.normalize_scene(sc), sc)


if __name__ == "__main__":
    unittest.main()
