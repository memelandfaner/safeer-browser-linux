"""»Odpri tukaj«: program z Android naprave v oknu Safeer Controla (pretok zaslona + miska in tipkovnica)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import safeer_control  # noqa: E402


def _control(odgovor):
    app = safeer_control.SafeerControl.__new__(safeer_control.SafeerControl)
    app.link = mock.Mock()
    app.link.ukaz_pocakaj.return_value = odgovor
    return app


class Pretoci(unittest.TestCase):
    def test_poslje_apps_launch_s_stream(self):
        app = _control({"ok": True, "data": {"package": "org.videolan.vlc", "stream": "pending"}})
        izid = app._naprave_metoda("Pretoci", ["tablica-1", "org.videolan.vlc"])
        app.link.ukaz_pocakaj.assert_called_once_with(
            "tablica-1", "apps.launch", {"app": "org.videolan.vlc", "stream": True})
        self.assertEqual((izid["ok"], izid["tu"]), (True, True))

    def test_starejsa_naprava_program_odpre_pri_sebi(self):
        # Pred 2.1.124 naprava stream prezre: program se odpre, zaslona pa ne deli.
        izid = _control({"ok": True, "data": {"package": "org.videolan.vlc"}})._naprave_metoda(
            "Pretoci", ["tv-1", "org.videolan.vlc"])
        self.assertEqual((izid["ok"], izid["tu"]), (True, False))

    def test_napaka_naprave(self):
        izid = _control({"ok": False, "koda": "ni_namescena"})._naprave_metoda("Pretoci", ["tv-1", "x.y"])
        self.assertEqual((izid["ok"], izid["tu"], izid["koda"]), (False, False, "ni_namescena"))

    def test_metoda_v_vmesniku_dbus(self):
        self.assertIn('<method name="Pretoci">', safeer_control.SafeerControl.VMESNIK_NAPRAVE)


if __name__ == "__main__":
    unittest.main()
