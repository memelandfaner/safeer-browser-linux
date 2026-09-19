# -*- coding: utf-8 -*-
"""Skok po gumbih s krizcem (core/link_fokus.py): izbira naslednjega elementa v smeri."""
import unittest

from core.link_fokus import izberi


def gumb(x, y):
    return (float(x), float(y), x - 10, y - 10, 20, 20)


# Mreza 3 x 3 kot tipkovnica kalkulatorja, razmik 100.
MREZA = [gumb(x, y) for y in (100, 200, 300) for x in (100, 200, 300)]


class Izbira(unittest.TestCase):
    def test_sosed_v_vsaki_smeri(self):
        sredina = (200.0, 200.0)
        self.assertEqual(izberi(MREZA, sredina, "desno")[:2], (300.0, 200.0))
        self.assertEqual(izberi(MREZA, sredina, "levo")[:2], (100.0, 200.0))
        self.assertEqual(izberi(MREZA, sredina, "gor")[:2], (200.0, 100.0))
        self.assertEqual(izberi(MREZA, sredina, "dol")[:2], (200.0, 300.0))

    def test_na_robu_ni_skoka(self):
        self.assertIsNone(izberi(MREZA, (300.0, 200.0), "desno"))

    def test_raje_v_isti_vrsti_kot_diagonalno(self):
        elementi = [gumb(260, 120), gumb(330, 200)]
        self.assertEqual(izberi(elementi, (200.0, 200.0), "desno")[:2], (330.0, 200.0))

    def test_izven_stozca_ce_drugega_ni(self):
        """Edini element desno, a precej visje: se vedno je boljse kot obstati."""
        self.assertEqual(izberi([gumb(230, 50)], (200.0, 200.0), "desno")[:2], (230.0, 50.0))

    def test_neznana_smer(self):
        self.assertIsNone(izberi(MREZA, (200.0, 200.0), "naprej"))


if __name__ == "__main__":
    unittest.main()
