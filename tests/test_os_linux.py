"""Safeer OS za racunalnik (preobleka cez Linux Mint): programi, sistem, datoteke in stran - brez zaslona."""
import os
import re
import tempfile
import unittest
from unittest import mock

from core import os_datoteke, os_programi, os_sistem

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _beri(*deli):
    with open(os.path.join(KOREN, *deli), encoding="utf-8") as f:
        return f.read()


def _pisi(pot, vsebina):
    with open(pot, "w", encoding="utf-8") as f:
        f.write(vsebina)


def _vnos(mapa, ime, vsebina):
    with open(os.path.join(mapa, ime), "w", encoding="utf-8") as f:
        f.write("[Desktop Entry]\nType=Application\n" + vsebina)


class Programi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mapa = os.path.join(self.tmp.name, "applications")
        os.makedirs(self.mapa)
        _vnos(self.mapa, "firefox.desktop", "Name=Firefox\nName[sl]=Firefox\nComment=Browse\nExec=firefox %u\nIcon=firefox\nCategories=Network;WebBrowser;\n")
        _vnos(self.mapa, "cinnamon-settings-themes.desktop", "Name=Themes\nExec=cinnamon-settings themes\nIcon=themes\nCategories=Settings;DesktopSettings;\nOnlyShowIn=X-Cinnamon;\n")
        _vnos(self.mapa, "kde-only.desktop", "Name=KDE stvar\nExec=kstvar\nOnlyShowIn=KDE;\n")
        _vnos(self.mapa, "skrit.desktop", "Name=Skrit\nExec=skrit\nNoDisplay=true\n")
        _vnos(self.mapa, "htop.desktop", "Name=htop\nExec=htop\nTerminal=true\n")
        _vnos(self.mapa, "ni-namescen.desktop", "Name=Manjka\nExec=manjka\nTryExec=ta-program-ne-obstaja-123\n")
        _vnos(self.mapa, "igra.desktop", "Name=Sah\nExec=sah\nCategories=Game;BoardGame;Settings;\n")
        _vnos(self.mapa, "safeer-os.desktop", "Name=Safeer OS\nExec=safeer-os\n")
        self.shramba = os_programi.Shramba(os.path.join(self.tmp.name, "os.json"))
        self.p = os_programi.Programi(self.shramba, mape=[self.mapa], namizja=["X-Cinnamon"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_seznam_kot_meni(self):
        ids = {e["id"]: e for e in self.p.seznam()}
        self.assertEqual(set(ids), {"firefox.desktop", "cinnamon-settings-themes.desktop", "igra.desktop"})
        self.assertEqual(ids["firefox.desktop"]["skupina"], "splet")
        self.assertEqual(ids["cinnamon-settings-themes.desktop"]["skupina"], "sistem")
        self.assertEqual(ids["igra.desktop"]["skupina"], "igre", "igra ostane igra, tudi z nastavitvami")

    def test_zagon_samo_s_seznama(self):
        zagnani = []
        self.assertTrue(self.p.zazeni("firefox.desktop", lambda pot: zagnani.append(pot) or True))
        self.assertEqual(zagnani, [os.path.join(self.mapa, "firefox.desktop")])
        for slab in ("../firefox.desktop", "/usr/share/applications/firefox.desktop", "skrit.desktop", "firefox", ""):
            self.assertFalse(self.p.zazeni(slab, lambda pot: True), slab)
        self.assertEqual(self.shramba.get("uporaba")["firefox.desktop"]["n"], 1)
        self.assertEqual([e for e in self.p.seznam() if e["id"] == "firefox.desktop"][0]["uporaba"], 1)

    def test_pripenjanje_se_shrani(self):
        self.p.pripni("firefox.desktop", True)
        self.p.pripni("ne-obstaja.desktop", True)
        self.assertEqual(os_programi.Shramba(self.shramba.pot).get("pripeti"), ["firefox.desktop"])
        self.p.pripni("firefox.desktop", False)
        self.assertEqual(os_programi.Shramba(self.shramba.pot).get("pripeti"), [])


class Sistem(unittest.TestCase):
    def test_baterija(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(os_sistem.baterija(d))
            os.makedirs(os.path.join(d, "BAT1"))
            _pisi(os.path.join(d, "BAT1", "capacity"), "87\n")
            _pisi(os.path.join(d, "BAT1", "status"), "Charging\n")
            self.assertEqual(os_sistem.baterija(d), {"odstotek": 87, "polni": True, "polna": False})

    def test_nmcli_ubezi(self):
        self.assertEqual(os_sistem._razdeli("wifi:connected:Moj\\:dom"), ["wifi", "connected", "Moj:dom"])

    def test_zvok_iz_pactl(self):
        izpisi = {"get-sink-volume": "Volume: front-left: 29491 /  45% / -20.81 dB,   front-right: 29491 /  45%",
                  "get-sink-mute": "Mute: no"}

        def zazeni(ukaz, cas=4.0):
            return izpisi.get(ukaz[1]) if ukaz[0] == "pactl" else None
        with mock.patch.object(os_sistem, "_zazeni", zazeni):
            self.assertEqual(os_sistem.zvok(), {"glasnost": 45, "utisan": False})

    def test_samo_znani_ukazi(self):
        pognani = []
        with mock.patch.object(os_sistem, "_v_ozadju", lambda u: pognani.append(u) or True), \
                mock.patch.object(os_sistem.shutil, "which", lambda x: "/usr/bin/" + x):
            self.assertTrue(os_sistem.odpri_nastavitve("themes"))
            self.assertTrue(os_sistem.odpri_nastavitve("posodobitve"))
            self.assertFalse(os_sistem.odpri_nastavitve("themes; rm -rf ~"))
            self.assertFalse(os_sistem.odpri_nastavitve("--help"))
            self.assertTrue(os_sistem.napajanje("zakleni"))
            self.assertFalse(os_sistem.napajanje("rm"))
        self.assertEqual(pognani, [["cinnamon-settings", "themes"], ["mintupdate"],
                                   ["cinnamon-screensaver-command", "--lock"]])


class Datoteke(unittest.TestCase):
    def test_mape_pregled_iskanje(self):
        with tempfile.TemporaryDirectory() as dom:
            os.makedirs(os.path.join(dom, ".config"))
            os.makedirs(os.path.join(dom, "Dokumenti", "Projekti"))
            os.makedirs(os.path.join(dom, ".skrito"))
            _pisi(os.path.join(dom, "Dokumenti", "porocilo.odt"), "x")
            _pisi(os.path.join(dom, ".skrito", "porocilo-skrito.odt"), "x")
            with open(os.path.join(dom, ".config", "user-dirs.dirs"), "w") as f:
                f.write('XDG_DOCUMENTS_DIR="$HOME/Dokumenti"\nXDG_MUSIC_DIR="$HOME/Glasba"\n')
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": os.path.join(dom, ".config")}):
                mape = os_datoteke.uporabniske_mape(dom)
            self.assertEqual([m["vrsta"] for m in mape], ["HOME", "DOCUMENTS"])
            r = os_datoteke.preglej(os.path.join(dom, "Dokumenti"))
            self.assertEqual([(e["ime"], e["mapa"], e["vrsta"]) for e in r["elementi"]],
                             [("Projekti", True, "mapa"), ("porocilo.odt", False, "dokument")])
            self.assertEqual(os_datoteke.preglej(os.path.join(dom, "ni"))["napaka"], "ni_mape")
            self.assertEqual([z["ime"] for z in os_datoteke.isci("POROC", dom)], ["porocilo.odt"])
            self.assertEqual(os_datoteke.isci("p", dom), [])


class Stran(unittest.TestCase):
    def test_elementi_in_prevodi(self):
        html = _beri("assets", "os", "index.html")
        js = _beri("assets", "os", "os.js")
        for oznaka in set(re.findall(r'\$\("([\w]+)"\)', js)):
            self.assertIn('id="%s"' % oznaka, html, oznaka)
        besedila = _beri("assets", "os", "besedila.js")
        bloki = re.split(r"\n  (sl|en|de|es|fr|it): \{", besedila)[1:]
        jeziki = dict(zip(bloki[0::2], bloki[1::2]))
        self.assertEqual(sorted(jeziki), ["de", "en", "es", "fr", "it", "sl"])
        kljuci = {j: set(re.findall(r'(?:^|[\s{,])"?([\w-]+)"?:\s*"', v)) for j, v in jeziki.items()}
        for j in jeziki:
            self.assertEqual(kljuci[j], kljuci["sl"], j)
        rabljeni = set(re.findall(r'data-t="([\w-]+)"', html)) | set(re.findall(r'\bt\("([\w-]+)"\s*[,)]', js))
        self.assertFalse(rabljeni - kljuci["sl"], rabljeni - kljuci["sl"])
        # Vsak modul in orodje iz os_sistem ima besedilo.
        for m in os_sistem.MODULI:
            self.assertIn("m_" + m, kljuci["sl"])
        for o in os_sistem.ORODJA:
            self.assertIn("o_" + o, kljuci["sl"])

    def test_most_metode(self):
        js = _beri("assets", "os", "os.js")
        py = _beri("safeer_os.py")
        for metoda in set(re.findall(r'klic\("(\w+)"', js)):
            self.assertIn('"%s":' % metoda, py, metoda)


if __name__ == "__main__":
    unittest.main()
