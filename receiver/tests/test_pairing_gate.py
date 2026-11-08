import os
import tempfile
import unittest
from secure_flow import ReceiverSecurity

class PairingGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sec = ReceiverSecurity(os.path.join(self.tmp.name, "secure.json"), "receiver-test")

    def tearDown(self):
        self.tmp.cleanup()

    def test_unpaired_hello_is_allowed_for_discovery(self):
        kind, payload = self.sec.route({"id": "h1", "t": "hello", "d": {}})
        self.assertEqual(kind, "plain")
        self.assertFalse(payload["paired"])
        self.assertEqual(payload["rid"], "receiver-test")

    def test_unpaired_display_command_is_rejected(self):
        kind, payload = self.sec.route({"id": "c1", "t": "apply_design", "d": {"x": 1}})
        self.assertEqual(kind, "plain")
        self.assertFalse(payload["ok"])
        self.assertIn("الاقتران الآمن", payload["result"])

    def test_pair_begin_is_allowed(self):
        kind, payload = self.sec.route({"id": "p1", "t": "pair_begin", "d": {"pub": "candidate"}})
        self.assertEqual(kind, "pair_begin")
        self.assertEqual(payload[0], "p1")

    def test_unpaired_emergency_is_rejected(self):
        kind, payload = self.sec.route({"id": "e1", "t": "emergency", "d": {"text": "test"}})
        self.assertEqual(kind, "plain")
        self.assertFalse(payload["ok"])

if __name__ == "__main__":
    unittest.main()
