"""Enotno iskanje Safeer Media: `files.search` po deljenih mapah Safeer Controla."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import link_daljinec, link_datoteke  # noqa: E402


def _datoteka(koren, rel, vsebina=b"x"):
    pot = os.path.join(koren, rel)
    os.makedirs(os.path.dirname(pot), exist_ok=True)
    with open(pot, "wb") as d:
        d.write(vsebina)
    return pot


class IskanjeVMapah(unittest.TestCase):
    def setUp(self):
        self._mapa = tempfile.TemporaryDirectory()
        self.koren = os.path.realpath(self._mapa.name)
        _datoteka(self.koren, "Pink Floyd/The Dark Side of the Moon/04 - Time.flac")
        _datoteka(self.koren, "Pink Floyd/The Wall/Another Brick.mp3")
        _datoteka(self.koren, "Drugo/Time - opombe.txt")
        _datoteka(self.koren, ".skrito/Pink Floyd Time.mp3")
        _datoteka(self.koren, "Filmi/Čas je zlato (2020).mkv")
        self.mape = link_datoteke.DeljeneMape([self.koren])

    def tearDown(self):
        self._mapa.cleanup()

    def test_mapa_izvajalca_in_ime_skladbe(self):
        z = self.mape.isci("Pink Floyd Time")
        self.assertEqual([v["name"] for v in z], ["04 - Time.flac"])
        self.assertEqual(z[0]["type"], "audio")
        self.assertEqual(z[0]["id"], "share:0:Pink Floyd/The Dark Side of the Moon/04 - Time.flac")
        self.assertEqual(z[0]["path"], "Pink Floyd/The Dark Side of the Moon")

    def test_samo_mediji_brez_skritih(self):
        imena = [v["name"] for v in self.mape.isci("time")]
        self.assertIn("04 - Time.flac", imena)
        self.assertNotIn("Time - opombe.txt", imena)       # ni medij
        self.assertNotIn("Pink Floyd Time.mp3", imena)     # skrita mapa

    def test_sumniki_in_predpona(self):
        self.assertEqual([v["name"] for v in self.mape.isci("cas zlat")], ["Čas je zlato (2020).mkv"])

    def test_boljsi_najprej(self):
        # "pink" je v mapi obeh; "brick" je v imenu samo ene.
        z = self.mape.isci("pink brick")
        self.assertEqual([v["name"] for v in z], ["Another Brick.mp3"])
        z = self.mape.isci("pink")
        self.assertEqual(len(z), 2)

    def test_povezava_ven_ni_zadetek(self):
        with tempfile.TemporaryDirectory() as zunaj:
            _datoteka(zunaj, "Pink Floyd Time.mp3")
            os.symlink(os.path.join(zunaj, "Pink Floyd Time.mp3"), os.path.join(self.koren, "Pink Floyd", "povezava - Time.mp3"))
            self.assertNotIn("povezava - Time.mp3", [v["name"] for v in self.mape.isci("pink floyd time")])

    def test_prazna_poizvedba_in_brez_map(self):
        self.assertEqual(self.mape.isci("  "), [])
        self.assertEqual(link_datoteke.DeljeneMape([]).isci("time"), [])


class VesRacunalnik(unittest.TestCase):
    def test_mape_z_mediji_ob_vesem_racunalniku(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as doma:
            doma = os.path.realpath(doma)
            glasba = os.path.join(doma, "Glasba")
            _datoteka(glasba, "Pink Floyd/Time.mp3")
            _datoteka(doma, "Zasebno/Pink Floyd Time.mp3")   # ne v mapi z mediji
            os.makedirs(os.path.join(doma, ".config"))
            with open(os.path.join(doma, ".config", "user-dirs.dirs"), "w") as d:
                d.write('XDG_MUSIC_DIR="$HOME/Glasba"\n')
            with mock.patch.dict(os.environ, {"HOME": doma}):
                brez = link_datoteke.DeljeneMape([]).isci("pink floyd time")
                mape = link_datoteke.DeljeneMape([], ves_disk=True)
                z = mape.isci("pink floyd time")
            self.assertEqual(brez, [])
            self.assertEqual([v["name"] for v in z], ["Time.mp3"])
            self.assertEqual(z[0]["id"], "disk:" + os.path.join(glasba, "Pink Floyd", "Time.mp3"))
            self.assertIsNotNone(mape.razresi(z[0]["id"]))  # streznik datoteko res da


class UkazFilesSearch(unittest.TestCase):
    def test_ukaz_poklice_iskanje_in_vrne_zadetke(self):
        klici = []

        class Lazne:
            def isci(self, q, posiljatelj, hub):
                klici.append((q, posiljatelj))
                return {"items": [{"id": "share:0:a.mp3", "name": "a.mp3", "type": "audio"}], "shared": True}

        izidi = []
        link_daljinec.izvedi_control("files.search", {"q": "pink floyd time"}, lambda u: None, izidi.append,
                                     datoteke=Lazne(), posiljatelj="tv-1")
        self.assertEqual(klici, [("pink floyd time", "tv-1")])
        self.assertTrue(izidi[0]["ok"])
        self.assertIn("files.search", link_daljinec.DEJANJA_DATOTEKE)

    def test_brez_deljenja(self):
        izidi = []
        link_daljinec.izvedi_control("files.search", {"q": "x"}, lambda u: None, izidi.append)
        self.assertFalse(izidi[0]["ok"])


if __name__ == "__main__":
    unittest.main()
