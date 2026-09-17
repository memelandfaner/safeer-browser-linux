"""Vnos s televizorja na racunalnik (core/link_vnos.py): samo dovoljeno in nic skozi lupino."""
import os
import sys
import unittest

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOREN)

from core import link_vnos  # noqa: E402


class Lazni(link_vnos.Vnos):
    """Namesto xdotool si ukaze samo zapomni."""

    def __init__(self):
        super().__init__(xdotool="/usr/bin/xdotool")
        self.ukazi = []

    def _pozeni(self, argumenti):
        self.ukazi.append(list(argumenti))
        self.stevec += 1
        return True


class Dovoljeno(unittest.TestCase):
    def setUp(self):
        self.v = Lazni()

    def test_tipke_s_seznama(self):
        self.assertTrue(self.v.izvedi({"vrsta": "tipka", "tipka": "gor"}))
        self.assertEqual(self.v.ukazi[-1], ["key", "--clearmodifiers", "Up"])
        self.assertTrue(self.v.izvedi({"vrsta": "tipka", "tipka": "OK"}))
        self.assertEqual(self.v.ukazi[-1][-1], "Return")

    def test_neznana_tipka_ne_gre_skozi(self):
        self.assertFalse(self.v.izvedi({"vrsta": "tipka", "tipka": "rm -rf"}))
        self.assertFalse(self.v.izvedi({"vrsta": "tipka", "tipka": "ctrl+alt+F2"}))
        self.assertEqual(self.v.ukazi, [])

    def test_neznana_vrsta_ne_gre_skozi(self):
        self.assertFalse(self.v.izvedi({"vrsta": "ukaz", "ukaz": "reboot"}))
        self.assertFalse(self.v.izvedi({}))
        self.assertFalse(self.v.izvedi({"vrsta": "tipka"}))
        self.assertEqual(self.v.ukazi, [])

    def test_besedilo_gre_za_dvojni_pomisljaj(self):
        self.assertTrue(self.v.izvedi({"vrsta": "besedilo", "besedilo": "safeer.si -rf; reboot"}))
        u = self.v.ukazi[-1]
        self.assertEqual(u[0], "type")
        self.assertIn("--", u)
        self.assertEqual(u[-1], "safeer.si -rf; reboot")     # kot en sam argument, ne skozi lupino

    def test_besedilo_brez_krmilnih_znakov_in_omejeno(self):
        self.assertFalse(self.v.izvedi({"vrsta": "besedilo", "besedilo": "a\nb"}))
        self.assertTrue(self.v.izvedi({"vrsta": "besedilo", "besedilo": "x" * 500}))
        self.assertEqual(len(self.v.ukazi[-1][-1]), link_vnos.NAJVEC_BESEDILA)

    def test_premik_je_omejen(self):
        self.assertTrue(self.v.izvedi({"vrsta": "premik", "dx": 5000, "dy": -5000}))
        self.assertEqual(self.v.ukazi[-1][-2:], [str(link_vnos.NAJVEC_PREMIK), str(-link_vnos.NAJVEC_PREMIK)])
        self.assertFalse(self.v.izvedi({"vrsta": "premik", "dx": "veliko", "dy": 0}))
        self.assertFalse(self.v.izvedi({"vrsta": "premik", "dx": 0, "dy": 0}))

    def test_kliki_in_kolesce(self):
        self.assertTrue(self.v.izvedi({"vrsta": "klik", "gumb": "desni"}))
        self.assertEqual(self.v.ukazi[-1][-1], "3")
        self.assertTrue(self.v.izvedi({"vrsta": "klik", "gumb": "levi", "dvojni": True}))
        self.assertIn("--repeat", self.v.ukazi[-1])
        self.assertFalse(self.v.izvedi({"vrsta": "klik", "gumb": "cetrti"}))
        self.assertTrue(self.v.izvedi({"vrsta": "kolesce", "smer": "dol", "koliko": 99}))
        self.assertEqual(self.v.ukazi[-1][2], "10")          # navzgor omejeno
        self.assertFalse(self.v.izvedi({"vrsta": "kolesce", "smer": "vstran"}))

    def test_brez_xdotool_ne_naredi_nicesar(self):
        v = link_vnos.Vnos(xdotool="")
        self.assertFalse(v.mozno)
        self.assertFalse(v.izvedi({"vrsta": "tipka", "tipka": "gor"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
