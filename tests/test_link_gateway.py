"""Gateway v0.1: racunalnik sodeluje pri izvolitvi huba po istem pravilu kot Android
(IzvolitevHuba): visja prioriteta, pri enaki manjsi id; steje samo clan kroga zaupanja.

Prej je racunalnik gostil samo, kadar drugega huba ni, televizor pa se je racunalniku (80 > 60)
umaknil - ob hkratnem zagonu sta se lahko umaknila oba in hisa je ostala brez sredisca.
"""
import unittest

from core import link_hub_streznik as s
from tests.test_link_hub_gostitelj import LazniOglas, LazniStreznik

TV = {"naslov": "wss://tv", "id": "n-tv", "prio": 60, "fp": "cd" * 32, "tls": True}
STREZNIK = {"naslov": "wss://nas", "id": "n-nas", "prio": 100, "fp": "ef" * 32, "tls": True}
DRUGI_PC = {"naslov": "wss://pc2", "id": "n-aaa", "prio": 80, "fp": "12" * 32, "tls": True}


def clan(*idji):
    return lambda i: i in idji


class Pravilo(unittest.TestCase):
    def test_je_pred_kot_na_androidu(self):
        self.assertTrue(s.je_pred(80, "n-pc", 60, "n-tv"))
        self.assertFalse(s.je_pred(60, "n-tv", 80, "n-pc"))
        self.assertTrue(s.je_pred(80, "n-aaa", 80, "n-pc"), "pri enaki prioriteti manjsi id")
        self.assertFalse(s.je_pred(80, "n-pc", 80, "n-pc"), "sam pred seboj ni nihce")

    def test_televizor_ni_boljsi_od_racunalnika(self):
        self.assertIsNone(s.boljsi_hub([TV], "n-pc", clan=clan("n-tv")))

    def test_domaci_streznik_je_boljsi(self):
        self.assertEqual(s.boljsi_hub([TV, STREZNIK], "n-pc", clan=clan("n-tv", "n-nas"))["id"], "n-nas")

    def test_drug_racunalnik_z_manjsim_id(self):
        self.assertEqual(s.boljsi_hub([DRUGI_PC], "n-pc", clan=clan("n-aaa"))["id"], "n-aaa")

    def test_tuj_oglas_nima_glasu(self):
        self.assertIsNone(s.boljsi_hub([STREZNIK], "n-pc", clan=clan()), "streznik zunaj kroga ne steje")

    def test_nas_oglas_ni_tekmec(self):
        nas = {"naslov": "wss://pc", "id": "n-pc", "prio": 80, "fp": "ab" * 32}
        self.assertIsNone(s.boljsi_hub([nas], "n-pc", "ab" * 32, clan=clan("n-pc")))
        self.assertIsNone(s.boljsi_hub([dict(nas, id="")], "", "ab" * 32, clan=clan()))

    def test_starejsi_hub_brez_prioritete(self):
        self.assertIsNone(s.boljsi_hub([{"naslov": "wss://x", "id": "n-0", "fp": ""}], "n-pc", clan=clan("n-0")))


class Gostitelj(unittest.TestCase):
    def _g(self, oglaseni, clani, streznik=None, oglas=None):
        return s.HubGostitelj(poisci=lambda: oglaseni[0] if oglaseni else None,
                              streznik=streznik or LazniStreznik(), oglas=oglas or LazniOglas(),
                              hubi=lambda: list(oglaseni), clan=clan(*clani), nas_id=lambda: "n-pc")

    def test_prevzame_od_televizorja(self):
        st, og = LazniStreznik(), LazniOglas()
        g = self._g([TV], ["n-tv"], st, og)
        self.assertTrue(g.preveri(), "racunalnik (80) prevzame, televizor (60) se umakne")
        self.assertEqual(st.zagoni, 1)
        self.assertEqual(og.zacetki[0][2] != "", True)

    def test_ne_umakne_se_televizorju_ko_ze_gosti(self):
        st = LazniStreznik()
        oglaseni = []
        g = self._g(oglaseni, ["n-tv"], st)
        self.assertTrue(g.preveri())
        oglaseni.append(TV)      # televizor se vrne in za trenutek gosti tudi on
        self.assertTrue(g.preveri(), "prej sta se lahko umaknila oba - zdaj ostane boljsi")
        self.assertEqual(st.ustavitve, 0)

    def test_umakne_se_domacemu_strezniku(self):
        st, og = LazniStreznik(), LazniOglas()
        oglaseni = []
        g = self._g(oglaseni, ["n-nas"], st, og)
        self.assertTrue(g.preveri())
        oglaseni.append(STREZNIK)
        self.assertFalse(g.preveri())
        self.assertEqual((st.ustavitve, og.konci), (1, 1))

    def test_brez_mdns_velja_staro_pravilo(self):
        st = LazniStreznik()
        g = s.HubGostitelj(poisci=lambda: {"naslov": "wss://tv", "id": "n-tv"}, streznik=st, oglas=LazniOglas(),
                           hubi=lambda: [], clan=clan("n-tv"), nas_id=lambda: "n-pc")
        self.assertFalse(g.preveri(), "brez oglasov s prioriteto ne vemo, kdo je boljsi - ne prevzemamo")


if __name__ == "__main__":
    unittest.main()
