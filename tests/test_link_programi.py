"""Programi racunalnika za televizor (core/link_programi.py): dovoljenje, branje .desktop, varen zagon."""
import os
import shutil
import sys
import tempfile
import unittest

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOREN)

from core import link_daljinec, link_programi  # noqa: E402


def zapisi(mapa, ime, vsebina):
    with open(os.path.join(mapa, ime), "w", encoding="utf-8") as d:
        d.write(vsebina)


class Seznam(unittest.TestCase):
    def setUp(self):
        self.mapa = tempfile.mkdtemp(prefix="safeer-programi-")
        aplikacije = os.path.join(self.mapa, "applications")
        os.makedirs(aplikacije)
        zapisi(aplikacije, "urejevalnik.desktop",
               "[Desktop Entry]\nType=Application\nName=Urejevalnik\nComment=Pisanje\nExec=urejevalnik %U\nIcon=urejevalnik\n")
        zapisi(aplikacije, "skrit.desktop",
               "[Desktop Entry]\nType=Application\nName=Skrit\nNoDisplay=true\nExec=skrit\n")
        zapisi(aplikacije, "konzola.desktop",
               "[Desktop Entry]\nType=Application\nName=Konzola\nTerminal=true\nExec=htop\n")
        zapisi(aplikacije, "nastavitve.desktop",
               "[Desktop Entry]\nType=Application\nName=Nastavitve sistema\nCategories=Settings;\nExec=nastavitve\n")
        zapisi(aplikacije, "manjka.desktop",
               "[Desktop Entry]\nType=Application\nName=Ni namescen\nTryExec=/ni/tega/programa\nExec=ni\n")
        zapisi(aplikacije, "povezava.desktop",
               "[Desktop Entry]\nType=Link\nName=Povezava\nURL=https://safeer.si\n")
        # Testna mapa namesto pravih vnosov racunalnika (ta ima svoje programe).
        self.aplikacije = [aplikacije]

    def tearDown(self):
        shutil.rmtree(self.mapa, ignore_errors=True)

    def test_brez_dovoljenja_ni_seznama(self):
        p = link_programi.Programi(False, self.aplikacije)
        self.assertEqual(p.seznam(), {"enabled": False, "items": []})
        self.assertFalse(p.zazeni("app:urejevalnik.desktop"), "brez dovoljenja se nic ne zazene")

    def test_seznam_pokaze_le_smiselne_programe(self):
        p = link_programi.Programi(True, self.aplikacije)
        podatki = p.seznam(z_ikonami=False)
        self.assertTrue(podatki["enabled"])
        imena = [v["name"] for v in podatki["items"]]
        self.assertEqual(imena, ["Urejevalnik"],
                         "skriti, konzolni, sistemski in nenamesceni vnosi ne gredo na televizor")
        self.assertEqual(podatki["items"][0]["id"], "app:urejevalnik.desktop")
        self.assertEqual(podatki["items"][0]["comment"], "Pisanje")

    def test_zazene_samo_kar_je_na_seznamu(self):
        p = link_programi.Programi(True, self.aplikacije)
        p.seznam(z_ikonami=False)
        for oznaka in ("app:../../etc/passwd", "app:/usr/share/applications/firefox.desktop",
                       "urejevalnik.desktop", "app:skrit.desktop", "app:ni-takega.desktop", ""):
            self.assertFalse(p.zazeni(oznaka), f"oznaka {oznaka!r} se ne sme zagnati")

    def test_izklop_pocisti_seznam(self):
        p = link_programi.Programi(True, self.aplikacije)
        p.seznam(z_ikonami=False)
        p.nastavi(False)
        self.assertEqual(p.seznam(), {"enabled": False, "items": []})


class Ukazi(unittest.TestCase):
    """Ukaza `apps.list` in `apps.launch` prek daljinca Safeer Controla."""

    def odgovor(self, dejanje, parametri=None, programi=None):
        izidi = []
        link_daljinec.izvedi_control(dejanje, parametri or {}, lambda _u: None, izidi.append,
                                     programi=programi)
        return izidi[0]

    def test_brez_modula_razumljiva_napaka(self):
        for dejanje in ("apps.list", "apps.launch"):
            i = self.odgovor(dejanje)
            self.assertFalse(i["ok"])
            self.assertEqual(i["code"], "ni_na_racunalniku")

    def test_izklopljeno_vrne_prazen_seznam(self):
        i = self.odgovor("apps.list", programi=link_programi.Programi(False))
        self.assertTrue(i["ok"])
        self.assertFalse(i["data"]["enabled"])
        self.assertEqual(i["data"]["items"], [])

    def test_zagon_neznanega_programa(self):
        i = self.odgovor("apps.launch", {"app": "app:cesar-ni.desktop"}, programi=link_programi.Programi(True))
        self.assertFalse(i["ok"])
        self.assertEqual(i["code"], "ni_programa")


if __name__ == "__main__":
    unittest.main()
