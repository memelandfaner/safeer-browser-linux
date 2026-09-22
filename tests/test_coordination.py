"""Safeer Coordination (services/coordination): avtentikacija, meje in cistost signalov."""
import hashlib
import hmac
import importlib.util
import os
import unittest

_POT = os.path.join(os.path.dirname(__file__), "..", "services", "coordination", "safeer_coordination.py")
_spec = importlib.util.spec_from_file_location("safeer_coordination", _POT)
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)


class Koordinacija(unittest.TestCase):
    def setUp(self):
        self.stara = c.SECRET
        c.SECRET = b"test-secret"
        c.records.clear()
        c.signals.clear()

    def tearDown(self):
        c.SECRET = self.stara

    def test_avtentikacija(self):
        tok = hmac.new(b"test-secret", b"phone-1", hashlib.sha256).hexdigest()
        self.assertTrue(c._auth("phone-1", tok))
        self.assertFalse(c._auth("phone-1", "bad"))
        self.assertFalse(c._auth("tv-1", tok))

    def test_brez_skrivnosti_je_izklopljena(self):
        c.SECRET = b""
        self.assertFalse(c._auth("d", "x"))

    def test_prisotnost_meje(self):
        self.assertEqual(c.objavi_prisotnost("d", {"public_key_fingerprint": "fp", "ttl": "x"})[0], 400)
        self.assertEqual(c.objavi_prisotnost("d", {"public_key_fingerprint": ""})[0], 400)
        koda, telo = c.objavi_prisotnost("d", {"public_key_fingerprint": "fp", "ttl": 9999})
        self.assertEqual((koda, telo["ttl"]), (200, c.TTL_MAX))

    def test_signali_omejeni_in_ne_sebi(self):
        self.assertEqual(c.poslji_signal("a", {"to": "a", "payload": {}})[0], 400)
        for _ in range(c.NAJVEC_SIGNALOV):
            self.assertEqual(c.poslji_signal("a", {"to": "b", "payload": {"x": 1}})[0], 202)
        self.assertEqual(c.poslji_signal("a", {"to": "b", "payload": {"x": 1}})[0], 429)
        self.assertEqual(c.poslji_signal("a", {"to": "c", "payload": "x" * 40000})[0], 413)

    def test_potekli_zapisi_odpadejo(self):
        c.objavi_prisotnost("d", {"public_key_fingerprint": "fp"})
        c._clean(now=c.records["d"]["expires_at"])
        self.assertNotIn("d", c.records)


if __name__ == "__main__":
    unittest.main()
