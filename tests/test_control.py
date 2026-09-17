"""Safeer Control (namizna aplikacija): paket, ukazi brez brskalnika in stran v nacinu Control."""
import os
import subprocess
import sys
import tempfile
import unittest

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOREN)

from core import link_daljinec  # noqa: E402


class ControlUkazi(unittest.TestCase):
    def _izvedi(self, dejanje, parametri=None, odpri=None):
        izidi = []
        link_daljinec.izvedi_control(dejanje, parametri or {}, odpri or (lambda u: None), izidi.append)
        self.assertEqual(len(izidi), 1)
        return izidi[0]

    def test_stanje(self):
        i = self._izvedi("status")
        self.assertTrue(i["ok"])
        self.assertEqual(i["data"]["app"], "safeer-control-linux")
        self.assertEqual(i["data"]["actions"], ["open_url", "volume", "status"])
        self.assertEqual(i["data"]["keys"], [])
        self.assertTrue(i["data"]["version"])

    def test_odpri_samo_http(self):
        odprti = []
        i = self._izvedi("open_url", {"url": "https://safeer.si/"}, odprti.append)
        self.assertTrue(i["ok"])
        self.assertEqual(odprti, ["https://safeer.si/"])
        i = self._izvedi("open_url", {"url": "file:///etc/passwd"}, odprti.append)
        self.assertFalse(i["ok"])
        self.assertEqual(len(odprti), 1)

    def test_kar_rabi_brskalnik_vrne_razumljivo_napako(self):
        for dejanje in ("key", "scroll", "screenshot", "restart", "clear_cache"):
            i = self._izvedi(dejanje, {"key": "ok"})
            self.assertFalse(i["ok"], dejanje)
            self.assertEqual(i["code"], "ni_v_ospredju")
        self.assertEqual(self._izvedi("nekaj")["code"], "neznano_dejanje")


class ControlPaket(unittest.TestCase):
    def test_payload_brez_brskalnika(self):
        with tempfile.TemporaryDirectory() as mapa:
            subprocess.run(["bash", os.path.join(KOREN, "packaging", "install_control_payload.sh"), mapa + "/usr"],
                           check=True, capture_output=True)
            lib = os.path.join(mapa, "usr", "lib", "safeer-control")
            for pot in ("safeer_control.py", "core/safeer_link.py", "core/link_hub.py", "core/link_tls.py",
                        "core/link_deljenje.py", "core/link_daljinec.py", "core/spake2.py",
                        "assets/link/index.html", "assets/link/link.js", "assets/link/daljinec.js",
                        "packaging/VERSION_CONTROL"):
                self.assertTrue(os.path.isfile(os.path.join(lib, pot)), pot)
            self.assertFalse(os.path.exists(os.path.join(lib, "safeer_mint.py")))
            self.assertFalse(os.path.exists(os.path.join(lib, "core", "adblock.py")))
            self.assertTrue(os.path.isfile(os.path.join(mapa, "usr", "bin", "safeer-control")))
            self.assertTrue(os.path.isfile(os.path.join(mapa, "usr", "share", "applications", "safeer-control.desktop")))
        # Control se predstavi s svojo razlicico, tudi brez GTK (izpis pred uvozom okna ni potreben: --version).
        v = open(os.path.join(KOREN, "packaging", "VERSION_CONTROL"), encoding="utf-8").read().strip()
        self.assertRegex(v, r"^\d+\.\d+\.\d+$")

    def test_stran_pozna_nacin_control(self):
        js = open(os.path.join(KOREN, "assets", "link", "link.js"), encoding="utf-8").read()
        self.assertIn("stanje.control = !!s.control", js)
        self.assertIn("function narisiControl()", js)
        for id_ in ("gumbZapri", "panelCast", "panelSync", "predvajalnik"):
            self.assertIn('pokazi("%s", false)' % id_, js)


if __name__ == "__main__":
    unittest.main()
