"""Protocol v1: model naprave, ki ga racunalnik pove v cast.register (core/link_hub.model_naprave_v1)."""
import sys
import unittest

from core import link_hub


class ModelNapraveV1(unittest.TestCase):
    def test_control_in_brskalnik(self):
        c = link_hub.model_naprave_v1("pc-abc-control")
        self.assertEqual(c["protocol"], "1.0")
        self.assertEqual(c["platform"], "linux")
        self.assertEqual(c["kind"], "control")
        b = link_hub.model_naprave_v1("pc-abc")
        self.assertEqual(b["kind"], "computer")
        self.assertNotIn("priority", b, "racunalnik huba ne gosti, prioritete ne poslje")

    def test_razlicica_iz_glavnega_modula(self):
        glavni = sys.modules["__main__"]
        prej = getattr(glavni, "APP_VERSION", None)
        try:
            glavni.APP_VERSION = "9.9.9"
            self.assertEqual(link_hub.model_naprave_v1("pc-x")["version"], "9.9.9")
            glavni.APP_VERSION = ""
            self.assertNotIn("version", link_hub.model_naprave_v1("pc-x"))
        finally:
            if prej is None:
                delattr(glavni, "APP_VERSION")
            else:
                glavni.APP_VERSION = prej


if __name__ == "__main__":
    unittest.main()
