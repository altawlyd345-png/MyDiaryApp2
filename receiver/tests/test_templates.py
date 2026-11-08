import unittest
import templates

class TemplateTests(unittest.TestCase):
    def test_catalog(self):
        items = templates.load_templates()
        self.assertGreaterEqual(len(items), 6)
        self.assertEqual(len(templates.template_scene("grid-4")["zones"]), 4)
    def test_invalid_transition_falls_back(self):
        self.assertEqual(templates.normalize_transition("surprise"), "none")
    def test_transition_duration_is_clamped(self):
        self.assertEqual(templates.transition_options({"transition_ms":99999})["transition_ms"], 3000)

if __name__ == "__main__":
    unittest.main()
