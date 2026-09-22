"""Global Link na racunalniku (core/link_rele.py): podpis zahtev, seznam dovoljenih, maskiranje okvirjev."""
import base64
import hashlib
import os
import subprocess
import tempfile
import unittest

from core import link_krog, link_rele


class Rele(unittest.TestCase):
    def test_podpis_preveri_isti_kljuc(self):
        with tempfile.TemporaryDirectory() as d:
            kljuc = os.path.join(d, "k.pem")
            subprocess.run(["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", kljuc], check=True)
            javni = base64.b64encode(subprocess.run(["openssl", "pkey", "-in", kljuc, "-pubout", "-outform", "DER"],
                                                    check=True, capture_output=True).stdout).decode()
            podpisi = lambda b: base64.b64encode(subprocess.run(["openssl", "dgst", "-sha256", "-sign", kljuc],
                                                               input=b, check=True, capture_output=True).stdout).decode()
            g = link_rele.podpisane_glave("GET", "/v1/listen", b"", kljuc=lambda: javni, podpisi=podpisi, cas=1700000000)
            self.assertEqual(g["X-Safeer-Key"], javni)
            sporocilo = ("GET\n/v1/listen\n1700000000\n" + hashlib.sha256(b"").hexdigest()).encode()
            self.assertTrue(link_krog.preveri_podpis(javni, sporocilo, g["X-Safeer-Signature"]))
            self.assertEqual(link_rele.id_iz_kljuca(javni), link_krog.id_iz_kljuca(javni))

    def test_dovoljeni_samo_veljavni_clani_brez_nas(self):
        k1, k2, k3 = (base64.b64encode(os.urandom(91)).decode() for _ in range(3))
        krog = {"clani": {"a": {"kljuc": k1, "dodano": 1}, "b": {"kljuc": k2, "dodano": 1}, "c": {"kljuc": k3, "dodano": 9}},
                "umiki": {"b": {"umaknjeno": 5}, "c": {"umaknjeno": 5}}}
        nas = link_rele.id_iz_kljuca(k1)
        self.assertEqual(link_rele.dovoljeni_iz_kroga(krog, nas), [link_rele.id_iz_kljuca(k3)])

    def test_maskiranje(self):
        m, d = os.urandom(4), os.urandom(5000)
        self.assertEqual(link_rele._maskiraj(d, m), bytes(b ^ m[i % 4] for i, b in enumerate(d)))
        self.assertEqual(link_rele._maskiraj(b"", m), b"")

    def test_najdi_hub_prek_releja_zaupa_samo_kljucu_iz_kroga(self):
        from unittest import mock
        from core import link_tls
        k_nas, k_tv, k_tab = (base64.b64encode(os.urandom(91)).decode() for _ in range(3))
        krog = {"clani": {"a": {"kljuc": k_nas, "dodano": 1}, "b": {"kljuc": k_tv, "dodano": 1},
                          "c": {"kljuc": k_tab, "dodano": 1}}}
        nas, tv, tab = (link_rele.id_iz_kljuca(k) for k in (k_nas, k_tv, k_tab))
        poskusi, zaprti = [], []

        class Rele:
            def __init__(self, cilj, kljuc=None, podpisi=None):
                self.cilj, self.vrata = cilj, 1000 + len(poskusi)
                poskusi.append(cilj)

            def zapri(self):
                zaprti.append(self.cilj)

        # Tablica se oglasi s tujim kljucem (ne sme dobiti zaupanja), TV s pravim.
        potrdila = {1000: ("fp-tab", k_nas), 1001: ("fp-tv", k_tv)}
        link_rele._ODSOTNI.clear()
        with mock.patch.object(link_rele, "LokalniRele", Rele), \
                mock.patch.object(link_tls, "potrdilo_huba", lambda n, timeout=0: potrdila.get(int(n.split(":")[2].strip("/")), ("", ""))):
            cilj, rele, odtis = link_rele.najdi_hub_prek_releja(krog, nas, prednost=[tab], zdaj=100.0)
            self.assertEqual((cilj, odtis), (tv, "fp-tv"))
            self.assertEqual(poskusi, [tab, tv])            # prednost najprej, nas nikoli
            self.assertEqual(zaprti, [tab])
            # Tablica je minuto odsotna: ne klicemo je znova (kvota Workerja).
            poskusi.clear()
            potrdila = {1000: ("fp-tv", k_tv)}
            self.assertEqual(link_rele.najdi_hub_prek_releja(krog, nas, prednost=[tab], zdaj=130.0)[0], tv)
            self.assertEqual(poskusi, [tv])
        link_rele._ODSOTNI.clear()


if __name__ == "__main__":
    unittest.main()
