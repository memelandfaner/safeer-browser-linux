# -*- coding: utf-8 -*-
"""Locen zaslon za televizor (core/link_sway.py): brez zagona swaya, samo dogovori in izbire."""
import os
import struct
import tempfile
import unittest

from core import link_daljinec, link_programi, link_sway, link_zaslon
from core.link_vnos import TIPKE


class LazniDrugi:
    """Namesto swaya: zapomni si, kaj bi zagnal, in pove, koliko oken ima."""

    def __init__(self, tece=True, okna=0):
        self._tece, self._okna = tece, okna
        self.zagnani = []
        self.vnos = object()
        self.velikosti = []

    def tece(self):
        return self._tece

    def okna(self):
        return self._okna

    def pokazi(self, pidi):
        return False

    def zazeni_program(self, argv):
        self.zagnani.append(list(argv))
        return True

    def velikost(self, s, v):
        self.velikosti.append((s, v))


class Tipke(unittest.TestCase):
    def test_vse_tipke_televizorja_imajo_kodo(self):
        """Vsaka tipka, ki jo televizor sme poslati, mora imeti tudi kodo za drugi zaslon."""
        for oznaka in TIPKE:
            self.assertIsNotNone(link_sway.SwayVnos._kode(oznaka), oznaka)

    def test_bliznjica_je_vec_tipk(self):
        self.assertEqual(link_sway.SwayVnos._kode("shrani_kot"), [29, 42, 31])
        self.assertIsNone(link_sway.SwayVnos._kode("rm -rf"))

    def test_niz_wayland_je_poravnan(self):
        b = link_sway._niz("wl_seat")
        self.assertEqual(struct.unpack("=I", b[:4])[0], 8)
        self.assertEqual(len(b) % 4, 0)
        self.assertEqual(link_sway._fiksno(1.5), 384)


VSE = {"muxer": True, "no_damage": True, "codec_param": True, "framerate": True}


class Zajem(unittest.TestCase):
    def setUp(self):
        link_sway._WF = dict(VSE)

    def tearDown(self):
        link_sway._WF = None

    def test_starejsi_wf_recorder_brez_neznanih_zastavic(self):
        """Starejsi wf-recorder ne pozna -D, -r in -p: teh ne posljemo, sicer bi zajem takoj padel."""
        link_sway._WF = {"muxer": True, "no_damage": False, "codec_param": False, "framerate": False}
        d = link_sway.DrugiZaslon(mapa=tempfile.mkdtemp())
        d.graficna = lambda: "/dev/dri/renderD128"
        u = d.ukaz_zajema(60, 16, "24M")
        for z in ("-D", "-r", "-p"):
            self.assertNotIn(z, u)
        self.assertIn("-m", u)

    def test_namestitev_samo_nasi_paketi(self):
        s = {"manjka": ["wtype", "rm -rf /"], "posodobitev": True, "orodja": True}
        self.assertEqual(link_sway.paketi_za_namestitev(s), ["wtype", "wf-recorder"])
        u = link_sway.ukaz_namestitve(s)
        self.assertEqual(u[0], "pkexec")
        self.assertTrue(u[-1].endswith("apt-get install -y wtype wf-recorder"))
        self.assertIsNone(link_sway.ukaz_namestitve({"manjka": [], "posodobitev": False, "orodja": True}))
        self.assertIsNone(link_sway.ukaz_namestitve({"manjka": ["sway"], "orodja": False}))

    def test_strojno_gol_h264_na_stdout(self):
        d = link_sway.DrugiZaslon(mapa=tempfile.mkdtemp())
        d.graficna = lambda: "/dev/dri/renderD128"
        u = d.ukaz_zajema(60, 16, "24M")
        self.assertEqual(u[:3], ["wf-recorder", "-o", link_sway.IZHOD])
        for par in (["-D"], ["-r", "60"], ["-m", "h264"], ["-f", "/dev/stdout"], ["-c", "h264_vaapi"]):
            self.assertTrue(any(u[i:i + len(par)] == par for i in range(len(u))), par)
        self.assertIn("qp=16", u)
        self.assertIn("bf=0", u)

    def test_programsko_4_2_0(self):
        """Brez -x yuv420p x264 kodira 4:4:4, tega pa televizor ne zna dekodirati."""
        d = link_sway.DrugiZaslon(mapa=tempfile.mkdtemp())
        d.graficna = lambda: None
        u = d.ukaz_zajema(30, 20, "8M")
        self.assertIn("libx264", u)
        self.assertEqual(u[u.index("-x") + 1], "yuv420p")

    def test_konfiguracija_brez_bliznjic(self):
        k = link_sway._konfiguracija(1280, 720)
        self.assertIn("resolution 1280x720", k)
        # Edina bliznjica je preklop med programi; nic, kar bi lahko zaprlo ali zagnalo karkoli.
        self.assertEqual([v for v in k.splitlines() if v.startswith("bindsym")],
                         ["bindsym Mod1+Tab fullscreen disable, focus right"])
        self.assertIn("xwayland enable", k)


class Izbira(unittest.TestCase):
    def test_kateri_zaslon(self):
        z = link_zaslon.Zaslon()
        self.assertFalse(z._na_drugem("apps"))              # brez drugega zaslona nikoli
        z.drugi = LazniDrugi(tece=False)
        self.assertFalse(z._na_drugem("apps"))
        z.drugi = LazniDrugi(tece=True, okna=0)
        self.assertTrue(z._na_drugem("apps"))
        self.assertFalse(z._na_drugem("desktop"))
        self.assertFalse(z._na_drugem(""))                  # star televizor, prazen drugi zaslon
        z.drugi = LazniDrugi(tece=True, okna=2)
        self.assertTrue(z._na_drugem(""))                   # star televizor mora okna videti
        self.assertFalse(z._na_drugem("desktop"))

    def test_program_gre_na_drugi_zaslon(self):
        mapa = tempfile.mkdtemp()
        with open(os.path.join(mapa, "urejevalnik.desktop"), "w", encoding="utf-8") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Urejevalnik\n"
                    "Exec=/usr/bin/urejevalnik --novo \"Moja mapa\" %U\n")
        p = link_programi.Programi(True, mape=[mapa])
        p.drugi = LazniDrugi()
        self.assertTrue(p.zazeni("app:urejevalnik.desktop"))
        self.assertEqual(p.drugi.zagnani, [["/usr/bin/urejevalnik", "--novo", "Moja mapa"]])
        self.assertEqual(p.drugi.zadnja_skupina, p._vnosi["urejevalnik.desktop"]["skupina"])
        # neznan program ne gre nikamor
        self.assertFalse(p.zazeni("app:ni.desktop"))
        self.assertEqual(len(p.drugi.zagnani), 1)

    def test_televizor_lahko_izbere_zaslon(self):
        izidi, klici = [], []

        class Z:
            def na_voljo(self):
                return {"dovoljeno": True, "mozno": True}

            def zacni(self, naprava, kakovost, cilj=""):
                klici.append(cilj)
                return {"screen": cilj}

        link_daljinec.izvedi_control("screen.start", {"screen": "Apps"}, lambda u: None, izidi.append, zaslon=Z())
        link_daljinec.izvedi_control("screen.start", {}, lambda u: None, izidi.append, zaslon=Z())
        self.assertEqual(klici, ["apps", ""])


class Brskalniki(unittest.TestCase):
    def test_prepoznava(self):
        from core.link_sway import _ime_brskalnika
        for ime in ("/usr/bin/brave-browser-stable", "google-chrome", "/opt/brave.com/brave/brave", "chromium"):
            self.assertTrue(_ime_brskalnika(ime), ime)
        for ime in ("gimp-2.10", "gnome-calculator", "firefox", ""):
            self.assertFalse(_ime_brskalnika(ime), ime)


if __name__ == "__main__":
    unittest.main()
