"""Hub na racunalniku: kdo sme noter, kam gre sporocilo in kaj dobi posiljatelj nazaj.

Tu je vsa logika, ki mora biti pravilna, zato je preizkusena brez vticnikov in TLS. Posebej
pazimo na sondo prijave, ki jo uporablja Safeer Control: prijavljena naprava mora dobiti
`isti_naprava`, osirotela vticnica pa `naprava_ni_povezana` - po tem odjemalec loci zivo povezavo
od mrtve in se po potrebi vrne.
"""
import json
import time
import unittest
from unittest import mock

from core import link_hub_streznik, link_krog


class LaznaPovezava:
    def __init__(self, naslov="192.168.0.50"):
        self.naslov = naslov
        self.poslano = []
        self.podatki = {}
        self.zaprta_z = None

    def poslji(self, besedilo):
        self.poslano.append(json.loads(besedilo))
        return True

    def zapri(self, koda=1000, razlog=""):
        self.zaprta_z = (koda, razlog)

    def zadnje(self, tip):
        for s in reversed(self.poslano):
            if s.get("type") == tip:
                return s
        return None


def _prijava(id_naprave, ime="Naprava", vloga="receiver", zmoznosti=("url", "remote")):
    return json.dumps({"id": "r1", "type": "cast.register",
                       "payload": {"device_id": id_naprave, "name": ime, "role": vloga,
                                   "capabilities": list(zmoznosti), "platform": "tv",
                                   "protocol": "1", "kind": "tv", "version": "2.1.119"}})


class Register(unittest.TestCase):
    def setUp(self):
        self.hub = link_hub_streznik.Hub(odtis="ab" * 32, nas_id="n-racunalnik")

    def test_prijava_in_seznam(self):
        p = LaznaPovezava()
        odgovor = json.loads(self.hub.obdelaj(p, _prijava("tv1", "Televizor")))
        self.assertEqual(odgovor["type"], "cast.ack")
        self.assertEqual(odgovor["status"], "accepted")
        self.assertEqual(odgovor["ref_id"], "r1")
        seznam = p.zadnje("cast.devices")
        self.assertIsNotNone(seznam)
        self.assertEqual([d["id"] for d in seznam["devices"]], ["tv1"])
        naprava = seznam["devices"][0]
        self.assertEqual(naprava["name"], "Televizor")
        self.assertEqual(naprava["platform"], "tv")
        self.assertEqual(naprava["ip"], "192.168.0.50")

    def test_brez_device_id_zavrnjeno(self):
        p = LaznaPovezava()
        odgovor = json.loads(self.hub.obdelaj(p, json.dumps({"id": "r1", "type": "cast.register", "payload": {}})))
        self.assertEqual(odgovor["status"], "rejected")
        self.assertEqual(odgovor["error_code"], "manjka_device_id")

    def test_nova_povezava_iste_naprave_zamenja_staro(self):
        stara, nova = LaznaPovezava(), LaznaPovezava()
        self.hub.obdelaj(stara, _prijava("tv1"))
        self.hub.obdelaj(nova, _prijava("tv1"))
        self.assertEqual(stara.zaprta_z, (1000, "nova povezava iste naprave"))
        self.assertEqual(self.hub.stevilo(), 1, "naprava ostane ena, ne dve")
        self.assertIs(self.hub.najdi("tv1").povezava, nova)

    def test_vstopnica_velja_samo_za_svojo_napravo(self):
        p = LaznaPovezava()
        p.podatki["id"] = "tv1"
        odgovor = json.loads(self.hub.obdelaj(p, _prijava("tablica")))
        self.assertEqual(odgovor["status"], "rejected")
        self.assertEqual(odgovor["error_code"], "vstopnica_ni_za_to_napravo")

    def test_odklop_osvezi_seznam(self):
        a, b = LaznaPovezava(), LaznaPovezava("192.168.0.60")
        self.hub.obdelaj(a, _prijava("tv1"))
        self.hub.obdelaj(b, _prijava("tablica"))
        self.hub.odklopi(a)
        seznam = b.zadnje("cast.devices")
        self.assertEqual([d["id"] for d in seznam["devices"]], ["tablica"])

    def test_ping_vrne_pong(self):
        p = LaznaPovezava()
        odgovor = json.loads(self.hub.obdelaj(p, json.dumps({"id": "p1", "type": "cast.ping"})))
        self.assertEqual(odgovor["type"], "cast.pong")
        self.assertEqual(odgovor["id"], "p1")

    def test_pokvarjeno_sporocilo_ne_podre_nicesar(self):
        p = LaznaPovezava()
        for smeti in ("{", "[]", "ni json", '"niz"'):
            odgovor = json.loads(self.hub.obdelaj(p, smeti))
            self.assertEqual(odgovor["status"], "rejected")


class Usmerjanje(unittest.TestCase):
    def setUp(self):
        self.hub = link_hub_streznik.Hub(odtis="ab" * 32)
        self.tv = LaznaPovezava("192.168.0.77")
        self.pc = LaznaPovezava("192.168.0.10")
        self.hub.obdelaj(self.tv, _prijava("tv1", "Televizor"))
        self.hub.obdelaj(self.pc, _prijava("pc1", "Racunalnik", vloga="sender"))

    def test_ukaz_pride_do_cilja_s_posiljateljem(self):
        odgovor = json.loads(self.hub.obdelaj(self.pc, json.dumps(
            {"id": "u1", "type": "control.command", "target": "tv1",
             "payload": {"action": "apps.launch"}})))
        self.assertEqual(odgovor["type"], "control.ack")
        self.assertEqual(odgovor["status"], "accepted")
        prejeto = self.tv.zadnje("control.command")
        self.assertEqual(prejeto["sender"], "pc1", "Hub mora vpisati posiljatelja")
        self.assertEqual(prejeto["payload"]["action"], "apps.launch")
        self.assertEqual(prejeto["id"], "u1", "id ukaza ostane isti (ref za odgovor)")

    def test_odgovora_hub_ne_potrjuje(self):
        self.assertIsNone(self.hub.obdelaj(self.tv, json.dumps(
            {"id": "o1", "type": "control.result", "target": "pc1", "payload": {"ok": True}})))
        self.assertIsNotNone(self.pc.zadnje("control.result"))

    def test_neznan_cilj_zavrnjen(self):
        odgovor = json.loads(self.hub.obdelaj(self.pc, json.dumps(
            {"id": "u1", "type": "control.command", "target": "telefon"})))
        self.assertEqual(odgovor["status"], "rejected")
        self.assertEqual(odgovor["error_code"], "ni_naprave")

    def test_sonda_prijavljene_naprave_dobi_isti_naprava(self):
        """Safeer Control po tem loci zivo prijavo od osirotele - mora biti natanko tako."""
        odgovor = json.loads(self.hub.obdelaj(self.pc, json.dumps(
            {"id": "sonda-prijave-1", "type": "control.command", "target": "pc1",
             "payload": {"action": "status"}})))
        self.assertEqual(odgovor["status"], "rejected")
        self.assertEqual(odgovor["error_code"], "isti_naprava")
        self.assertEqual(odgovor["ref_id"], "sonda-prijave-1")

    def test_sonda_osirotele_vticnice_dobi_naprava_ni_povezana(self):
        osirotela = LaznaPovezava()
        odgovor = json.loads(self.hub.obdelaj(osirotela, json.dumps(
            {"id": "sonda-prijave-2", "type": "control.command", "target": "tv1"})))
        self.assertEqual(odgovor["error_code"], "naprava_ni_povezana")

    def test_deljenje_je_v_svojem_prostoru(self):
        odgovor = json.loads(self.hub.obdelaj(self.pc, json.dumps(
            {"id": "d1", "type": "share.text", "target": "tv1", "payload": {"text": "zivjo"}})))
        self.assertEqual(odgovor["type"], "share.ack", "potrditev mora biti v prostoru share")
        self.assertEqual(self.tv.zadnje("share.text")["payload"]["text"], "zivjo")

    def test_brez_cilja_gre_vsem_drugim(self):
        self.hub.obdelaj(self.pc, json.dumps(
            {"id": "s1", "type": "sync.data", "payload": {"category": "bookmarks"}}))
        self.assertIsNotNone(self.tv.zadnje("sync.data"))
        self.assertIsNone(self.pc.zadnje("sync.data"), "posiljatelj sam sebi ne posilja")

    def test_katalog_aplikacij_se_objavi(self):
        self.hub.obdelaj(self.tv, json.dumps(
            {"id": "a1", "type": "apps.announce", "payload": {"apps": {"x": {"name": "X"}}}}))
        seznam = self.pc.zadnje("cast.devices")
        tv = [d for d in seznam["devices"] if d["id"] == "tv1"][0]
        self.assertEqual(tv["apps"], {"x": {"name": "X"}})


class PrijavaSPodpisom(unittest.TestCase):
    def setUp(self):
        self.hub = link_hub_streznik.Hub(odtis="AB" * 32)
        self.kljuc = link_krog.javni_kljuc_b64()
        self.clan = {"kljuc": self.kljuc, "ime": "Tablica", "platforma": "tablet"}

    def _izziv_in_podpis(self, device_id="n-0123456789abcdef"):
        izziv = self.hub.izziv(device_id)
        podatki = link_krog.podatki_za_podpis(izziv["fp"], izziv["nonce"], device_id)
        return izziv, link_krog.podpisi(podatki)

    def test_pravi_podpis_da_vstopnico(self):
        izziv, podpis = self._izziv_in_podpis()
        with mock.patch.object(link_krog, "krog") as k:
            k.return_value.clan_za_id.return_value = self.clan
            k.return_value.json.return_value = {"v": 1, "clani": {}}
            odgovor = self.hub.vstopnica_s_podpisom("n-0123456789abcdef", izziv["nonce"], podpis)
        self.assertIsNotNone(odgovor)
        self.assertTrue(odgovor["ticket"])
        self.assertEqual(odgovor["fp"], "ab" * 32, "odtis je vedno z malimi crkami")
        self.assertIn("ring", odgovor, "naprava mora dobiti krog, da pozna ostale")

    def test_vstopnica_velja_enkrat(self):
        izziv, podpis = self._izziv_in_podpis()
        with mock.patch.object(link_krog, "krog") as k:
            k.return_value.clan_za_id.return_value = self.clan
            k.return_value.json.return_value = {}
            odgovor = self.hub.vstopnica_s_podpisom("n-0123456789abcdef", izziv["nonce"], podpis)
        self.assertEqual(self.hub.porabi_vstopnico(odgovor["ticket"]), "n-0123456789abcdef")
        self.assertIsNone(self.hub.porabi_vstopnico(odgovor["ticket"]), "drugic ne velja")

    def test_izziv_velja_enkrat_tudi_ob_napacnem_podpisu(self):
        """Sicer bi lahko kdo na istem izzivu poskusal podpise, dokler eden ne bi ustrezal."""
        izziv, _ = self._izziv_in_podpis()
        with mock.patch.object(link_krog, "krog") as k:
            k.return_value.clan_za_id.return_value = self.clan
            self.assertIsNone(self.hub.vstopnica_s_podpisom("n-0123456789abcdef", izziv["nonce"], "napacen"))
        izziv2, podpis = self._izziv_in_podpis()
        with mock.patch.object(link_krog, "krog") as k:
            k.return_value.clan_za_id.return_value = self.clan
            k.return_value.json.return_value = {}
            self.assertIsNone(self.hub.vstopnica_s_podpisom("n-0123456789abcdef", izziv["nonce"], podpis),
                              "porabljen izziv ne sme vec veljati")

    def test_naprava_zunaj_kroga_ne_dobi_vstopnice(self):
        izziv, podpis = self._izziv_in_podpis()
        with mock.patch.object(link_krog, "krog") as k:
            k.return_value.clan_za_id.return_value = None
            self.assertIsNone(self.hub.vstopnica_s_podpisom("n-0123456789abcdef", izziv["nonce"], podpis))

    def test_tuj_nonce_ne_velja(self):
        self.hub.izziv("n-0123456789abcdef")
        with mock.patch.object(link_krog, "krog") as k:
            k.return_value.clan_za_id.return_value = self.clan
            self.assertIsNone(self.hub.vstopnica_s_podpisom("n-0123456789abcdef", "izmisljen", "x"))

    def test_izziv_za_drugo_napravo_ne_velja(self):
        izziv, podpis = self._izziv_in_podpis("n-0123456789abcdef")
        with mock.patch.object(link_krog, "krog") as k:
            k.return_value.clan_za_id.return_value = self.clan
            self.assertIsNone(self.hub.vstopnica_s_podpisom("n-ffffffffffffffff", izziv["nonce"], podpis))


class NapravaIzKljuca(unittest.TestCase):
    """Brskalnik in Control na istem racunalniku (isti kljuc) sta ena naprava: polje device je enako."""

    def test_sorodnika_imata_isto_napravo(self):
        kljuc = link_krog.javni_kljuc_b64()
        krog = link_krog.Krog()
        krog.dodaj("pc-x", kljuc, "Safeer (x)", "linux", "hub")
        krog.dodaj("pc-x-control", kljuc, "Safeer Control (x)", "linux", "pc-x")
        hub = link_hub_streznik.Hub(odtis="ab" * 32)
        hub.obdelaj(LaznaPovezava(), _prijava("pc-x", vloga="sender"))
        hub.obdelaj(LaznaPovezava(), _prijava("pc-x-control", vloga="sender"))
        hub.obdelaj(LaznaPovezava(), _prijava("tv-brez", vloga="receiver"))
        with mock.patch.object(link_krog, "krog", return_value=krog):
            naprave = {d["id"]: d for d in json.loads(hub.seznam_json())["devices"]}
        jedro = link_krog.id_iz_kljuca(kljuc)
        self.assertEqual(naprave["pc-x"].get("device"), jedro)
        self.assertEqual(naprave["pc-x-control"].get("device"), jedro)
        self.assertNotIn("device", naprave["tv-brez"], "brez kljuca v krogu ni naprave")

    def test_ime_iz_kroga(self):
        """Ime, ki ga je uporabnik dal na drugem hubu (v krogu), velja tudi na tem."""
        kljuc = link_krog.javni_kljuc_b64()
        krog = link_krog.Krog()
        krog.dodaj("tv-1", kljuc, "Dnevna soba", "tv", "hub")
        hub = link_hub_streznik.Hub(odtis="ab" * 32)
        hub.obdelaj(LaznaPovezava(), _prijava("tv-1", vloga="receiver"))
        with mock.patch.object(link_krog, "krog", return_value=krog):
            tv = json.loads(hub.seznam_json())["devices"][0]
        self.assertEqual(tv["name"], "Dnevna soba")
        self.assertNotEqual(tv["own_name"], "Dnevna soba")


class ImenaVKrogu(unittest.TestCase):
    def setUp(self):
        self.kljuc = link_krog.javni_kljuc_b64()
        self.krog = link_krog.Krog()
        self.krog.dodaj("tv-1", self.kljuc, "Safeer TV", "tv", "hub", dodano=100.0)

    def test_preimenuj_ne_premakne_dodano(self):
        self.assertTrue(self.krog.preimenuj("tv-1", "Dnevna soba"))
        c = self.krog.clan("tv-1")
        self.assertEqual((c["ime"], c["dodano"]), ("Dnevna soba", 100.0))

    def test_enako_ime_brez_casa_se_potrdi(self):
        self.assertTrue(self.krog.preimenuj("tv-1", "Safeer TV"))
        self.assertGreater(self.krog.clan("tv-1")["imenovano"], 0)
        self.assertFalse(self.krog.preimenuj("tv-1", "Safeer TV"))

    def test_novejsi_vpis_ohrani_ime(self):
        self.krog.preimenuj("tv-1", "Dnevna soba")
        self.krog.zdruzi({"clani": {"tv-1": {"kljuc": self.kljuc, "ime": "Safeer TV", "dodano": 200.0}}})
        self.assertEqual(self.krog.clan("tv-1")["ime"], "Dnevna soba")

    def test_imena_brez_novih_clanov_in_tujih_kljucev(self):
        tuj = {"clani": {"novi": {"kljuc": self.kljuc, "ime": "X", "imenovano": time.time()},
                         "tv-1": {"kljuc": "MFkw" + "A" * 80, "ime": "Ugrabljen", "imenovano": time.time()}}}
        self.assertFalse(self.krog.zdruzi_imena(tuj))
        self.assertIsNone(self.krog.clan("novi"))
        self.assertEqual(self.krog.clan("tv-1")["ime"], "Safeer TV")

    def test_umaknjena_se_ne_vrne(self):
        self.krog.umakni("tv-1", "hub", ob=time.time())
        self.assertFalse(self.krog.zdruzi_imena({"clani": {"tv-1": {"kljuc": self.kljuc, "ime": "Obujen",
                                                                   "imenovano": time.time() + 5}}}))
        self.assertIsNone(self.krog.clan("tv-1"))

    def test_hub_sprejme_trust_names(self):
        hub = link_hub_streznik.Hub(odtis="ab" * 32)
        tv, fon = LaznaPovezava(), LaznaPovezava()
        hub.obdelaj(tv, _prijava("tv-1", vloga="receiver"))
        hub.obdelaj(fon, _prijava("fon-1", vloga="sender"))
        ponudba = {"clani": {"tv-1": {"kljuc": self.kljuc, "ime": "Spalnica", "imenovano": time.time()}}}
        with mock.patch.object(link_krog, "krog", return_value=self.krog):
            odgovor = json.loads(hub.obdelaj(fon, json.dumps({"id": "t1", "type": "trust.names", "payload": ponudba})))
            seznam = json.loads(hub.seznam_json())["devices"]
        self.assertEqual(odgovor["status"], "accepted")
        self.assertEqual([d["name"] for d in seznam if d["id"] == "tv-1"], ["Spalnica"])
        self.assertTrue(tv.zadnje("trust.update"), "vsi dobijo nov krog")


class Zdravje(unittest.TestCase):
    def test_steje_prejemnike_in_posiljatelje(self):
        hub = link_hub_streznik.Hub(odtis="ab" * 32)
        hub.obdelaj(LaznaPovezava(), _prijava("tv1", vloga="receiver"))
        hub.obdelaj(LaznaPovezava(), _prijava("pc1", vloga="sender", zmoznosti=("sync",)))
        z = hub.zdravje()
        self.assertEqual((z["receivers"], z["senders"], z["sync_peers"]), (1, 1, 1))
        self.assertEqual(z["status"], "ok")


class Razsirljivost(unittest.TestCase):
    """Naprava iz leta 2028 se mora znati pogovarjati z Hubom iz leta 2026 in obratno.

    Pogoj je, da neznana polja nikogar ne podrejo: nova zmoznost se doda kot novo polje, stara
    stran ga preskoci in dela naprej s tistim, kar pozna. To je isto, kar je pri BitTorrentu
    razsiritev v rokovanju - le da tu ni treba nicesar dodajati, ker protokol to ze prenese.
    """

    def setUp(self):
        self.hub = link_hub_streznik.Hub(odtis="ab" * 32)

    def test_neznana_polja_v_prijavi_ne_motijo(self):
        p = LaznaPovezava()
        prijava = json.dumps({
            "id": "r1", "type": "cast.register", "nekaj_novega": {"x": 1},
            "payload": {"device_id": "novost", "name": "Naprava 2028", "role": "receiver",
                        "capabilities": ["url", "files", "neznana_zmoznost"],
                        "capability_versions": {"files": 3, "screen": 2},
                        "prihodnje_polje": [1, 2, 3]},
        })
        odgovor = json.loads(self.hub.obdelaj(p, prijava))
        self.assertEqual(odgovor["status"], "accepted", "neznana polja ne smejo zavrniti prijave")
        naprava = p.zadnje("cast.devices")["devices"][0]
        self.assertIn("neznana_zmoznost", naprava["capabilities"],
                      "neznano zmoznost posredujemo naprej, da jo razume, kdor jo pozna")

    def test_neznana_vrsta_sporocila_se_posreduje_naprej(self):
        """Hub ni razsodnik vsebine: sporocilo, ki ga ne pozna, mora priti do cilja."""
        a, b = LaznaPovezava(), LaznaPovezava("192.168.0.60")
        self.hub.obdelaj(a, _prijava("a1"))
        self.hub.obdelaj(b, _prijava("b1"))
        odgovor = json.loads(self.hub.obdelaj(a, json.dumps(
            {"id": "n1", "type": "prihodnost.novost", "target": "b1", "payload": {"kaj": "novo"}})))
        self.assertEqual(odgovor["status"], "accepted")
        self.assertEqual(odgovor["type"], "prihodnost.ack")
        prejeto = b.zadnje("prihodnost.novost")
        self.assertIsNotNone(prejeto, "neznano sporocilo mora priti do cilja nespremenjeno")
        self.assertEqual(prejeto["payload"], {"kaj": "novo"})

    def test_stara_naprava_brez_novih_polj_dela_naprej(self):
        """Naprava protokola 0.2 ne poslje platform/kind/version - to ne sme biti tezava."""
        p = LaznaPovezava()
        odgovor = json.loads(self.hub.obdelaj(p, json.dumps(
            {"id": "r1", "type": "cast.register",
             "payload": {"device_id": "stara", "name": "Naprava 2024", "role": "receiver"}})))
        self.assertEqual(odgovor["status"], "accepted")
        naprava = p.zadnje("cast.devices")["devices"][0]
        self.assertNotIn("platform", naprava, "praznih polj ne izmisljujemo")
        self.assertEqual(naprava["capabilities"], [])


class KrogPoHttp(unittest.TestCase):
    """Krog zaupanja gospodinjstva ni za vsakogar v omrezju: brez prijave ga ne da."""

    def test_krog_brez_prijave_ni_dostopen(self):
        o = link_hub_streznik._Obravnava.__new__(link_hub_streznik._Obravnava)
        o.path = "/cast/trust/ring"
        o._je_krajevni = lambda: True
        odgovori = []
        o._odgovori = lambda koda, telo: odgovori.append((koda, telo))
        o._napaka = lambda koda, sporocilo, oznaka: odgovori.append((koda, oznaka))
        with mock.patch.object(link_krog, "krog") as k:
            k.return_value.json.return_value = {"clani": {"skrivno": {}}}
            o.do_GET()
            k.assert_not_called()
        self.assertEqual(odgovori, [(401, "naprava_ni_seznanjena")])


if __name__ == "__main__":
    unittest.main()


class SeznanitevSKodo(unittest.TestCase):
    """Nova naprava se pridruzi Linku, katerega hub je racunalnik: koda na napravah v Linku, SPAKE2."""

    def setUp(self):
        self.hub = link_hub_streznik.Hub(odtis="cd" * 32, nas_id="n-racunalnik")
        self.tv = LaznaPovezava()
        self.hub.obdelaj(self.tv, _prijava("tv1", "Dnevna soba"))
        self.obvestila = []
        self.hub.ob_kodi = lambda ime, koda: self.obvestila.append((ime, koda))

    def _odjemalec(self, koda, zacetek, device_id="telefon1"):
        from core.spake2 import Spake2
        return Spake2.odjemalec(koda, device_id, zacetek["hub_id"], zacetek["fp"].encode(), zacetek["pair_id"].encode())

    def _seznani(self, koda_vnos, device_id="telefon1"):
        zacetek = self.hub.zacni_seznanitev(device_id, "Telefon")
        o = self._odjemalec(koda_vnos, zacetek, device_id)
        pa, ca, napaka = self.hub.spake_korak1(zacetek["pair_id"], device_id, o.sporocilo())
        self.assertIsNone(napaka)
        _, cb = o.zakljuci(pa)
        return zacetek, o.preveri(ca), self.hub.spake_korak2(zacetek["pair_id"], device_id, cb)

    def test_koda_na_televizorju_ne_pri_novi_napravi(self):
        zacetek = self.hub.zacni_seznanitev("telefon1", "Telefon")
        self.assertEqual(zacetek["nacin"], "spake2")
        self.assertNotIn("code", zacetek)
        self.assertNotIn("pin", zacetek)
        sporocilo = self.tv.zadnje("pair.code")
        self.assertEqual(sporocilo["payload"]["pair_id"], zacetek["pair_id"])
        self.assertEqual(sporocilo["payload"]["name"], "Telefon")
        self.assertEqual(len(sporocilo["payload"]["code"]), 6)
        self.assertEqual(self.obvestila, [("Telefon", sporocilo["payload"]["code"])])

    def test_prava_koda_da_zeton_vstopnico_in_vpis_v_krog(self):
        zacetek = self.hub.zacni_seznanitev("telefon1", "Telefon")
        koda = self.tv.zadnje("pair.code")["payload"]["code"]
        o = self._odjemalec(koda, zacetek)
        pa, ca, _ = self.hub.spake_korak1(zacetek["pair_id"], "telefon1", o.sporocilo())
        _, cb = o.zakljuci(pa)
        self.assertTrue(o.preveri(ca), "naprava preveri, da hub pozna isto kodo")
        zeton, napaka = self.hub.spake_korak2(zacetek["pair_id"], "telefon1", cb)
        self.assertIsNone(napaka)
        self.assertEqual(self.tv.zadnje("pair.done")["payload"]["pair_id"] if self._pocakaj("pair.done") else None,
                         zacetek["pair_id"])
        vstopnica = self.hub.vstopnica_z_zetonom(zeton)
        self.assertEqual(self.hub.porabi_vstopnico(vstopnica["ticket"]), "telefon1")
        krog = link_krog.Krog()
        kljuc = link_krog.javni_kljuc_b64()
        with mock.patch.object(link_krog, "krog", return_value=krog):
            odgovor, napaka = self.hub.vpisi_v_krog(zeton, kljuc, "Telefon (WP28 S)", "phone")
        self.assertIsNone(napaka)
        self.assertEqual(krog.clan("telefon1")["kljuc"], kljuc)
        self.assertEqual(krog.clan("telefon1")["dodal"], "n-racunalnik")
        self.assertIn("telefon1", self.tv.zadnje("trust.update")["payload"]["clani"])

    def _pocakaj(self, tip):
        for _ in range(50):
            if self.tv.zadnje(tip):
                return True
            time.sleep(0.02)
        return False

    def test_napacna_koda_in_meja_poskusov(self):
        zacetek = self.hub.zacni_seznanitev("telefon1", "Telefon")
        prava = self.tv.zadnje("pair.code")["payload"]["code"]
        napacna = "000000" if prava != "000000" else "111111"
        for i in range(link_hub_streznik.NAJVEC_POSKUSOV):
            o = self._odjemalec(napacna, zacetek)
            pa, ca, napaka = self.hub.spake_korak1(zacetek["pair_id"], "telefon1", o.sporocilo())
            if pa is None:
                self.assertEqual(napaka, "prevec_poskusov")
                break
            _, cb = o.zakljuci(pa)
            self.assertFalse(o.preveri(ca))
            zeton, napaka = self.hub.spake_korak2(zacetek["pair_id"], "telefon1", cb)
            self.assertIsNone(zeton)
            self.assertIn(napaka, ("napacna_koda", "prevec_poskusov"))
        self.assertEqual(napaka, "prevec_poskusov")
        o = self._odjemalec(prava, zacetek)
        self.assertEqual(self.hub.spake_korak1(zacetek["pair_id"], "telefon1", o.sporocilo())[2], "prijava_ne_obstaja")

    def test_tuj_device_id_ne_more_nadaljevati(self):
        zacetek = self.hub.zacni_seznanitev("telefon1", "Telefon")
        o = self._odjemalec("123456", zacetek, "vsiljivec")
        self.assertEqual(self.hub.spake_korak1(zacetek["pair_id"], "vsiljivec", o.sporocilo())[2], "prijava_ne_obstaja")

    def test_brez_zetona_ni_vstopnice_ne_vpisa(self):
        self.assertIsNone(self.hub.vstopnica_z_zetonom(""))
        self.assertIsNone(self.hub.vstopnica_z_zetonom("saf_pc_nic"))
        self.assertEqual(self.hub.vpisi_v_krog("saf_pc_nic", link_krog.javni_kljuc_b64(), "x", "phone")[1],
                         "naprava_ni_seznanjena")

    def test_zavrnitev_s_televizorja(self):
        zacetek = self.hub.zacni_seznanitev("telefon1", "Telefon")
        self.hub.obdelaj(self.tv, json.dumps({"id": "z1", "type": "pair.reject", "payload": {"pair_id": zacetek["pair_id"]}}))
        o = self._odjemalec("123456", zacetek)
        self.assertEqual(self.hub.spake_korak1(zacetek["pair_id"], "telefon1", o.sporocilo())[2], "prijava_ne_obstaja")

    def test_koda_potece(self):
        ura = [1000.0]
        hub = link_hub_streznik.Hub(odtis="cd" * 32, ura=lambda: ura[0])
        zacetek = hub.zacni_seznanitev("telefon1", "Telefon")
        ura[0] += link_hub_streznik.PIN_VELJA_S + 1
        o = self._odjemalec("123456", zacetek)
        self.assertEqual(hub.spake_korak1(zacetek["pair_id"], "telefon1", o.sporocilo())[2], "prijava_ne_obstaja")


class ZetoniPrezivijo(unittest.TestCase):
    def test_zeton_seznanitve_prezivi_ponovni_zagon(self):
        import os
        import tempfile
        mapa = tempfile.mkdtemp()
        pot = os.path.join(mapa, "hub-zetoni.json")
        hub = link_hub_streznik.Hub(odtis="cd" * 32, pot_zetonov=pot)
        tv = LaznaPovezava()
        hub.obdelaj(tv, _prijava("tv1"))
        zacetek = hub.zacni_seznanitev("telefon1", "Telefon")
        koda = tv.zadnje("pair.code")["payload"]["code"]
        from core.spake2 import Spake2
        o = Spake2.odjemalec(koda, "telefon1", zacetek["hub_id"], zacetek["fp"].encode(), zacetek["pair_id"].encode())
        pa, ca, _ = hub.spake_korak1(zacetek["pair_id"], "telefon1", o.sporocilo())
        _, cb = o.zakljuci(pa)
        zeton, _ = hub.spake_korak2(zacetek["pair_id"], "telefon1", cb)
        self.assertEqual(os.stat(pot).st_mode & 0o777, 0o600)
        nov = link_hub_streznik.Hub(odtis="cd" * 32, pot_zetonov=pot)
        self.assertEqual(nov.naprava_zetona(zeton), ("telefon1", "Telefon"))


class PridruzitevSQr(unittest.TestCase):
    """Vsaka naprava v Linku lahko pokaze QR za novo napravo; skrivnost naredi sredisce, hrani samo odtis."""

    def setUp(self):
        self.hub = link_hub_streznik.Hub(odtis="ef" * 32, nas_id="n-racunalnik")
        self.hub.naslov_za_qr = "192.168.0.135:8990"
        self.tv = LaznaPovezava()
        self.tv.podatki["id"] = "tv1"
        self.hub.obdelaj(self.tv, _prijava("tv1", "Dnevna soba"))

    def _povabilo(self):
        self.hub.obdelaj(self.tv, json.dumps({"id": "p1", "type": "pair.invite", "payload": {}}))
        return self.tv.zadnje("pair.invite.ok")["payload"]

    def test_televizor_dobi_kodo_in_naslov_sredisca(self):
        p = self._povabilo()
        self.assertEqual(p["address"], "192.168.0.135:8990")
        self.assertEqual(p["fp"], "ef" * 32)
        self.assertGreaterEqual(len(p["secret"]), 16)

    def test_prava_skrivnost_da_zeton_napacna_ne(self):
        p = self._povabilo()
        self.assertEqual(self.hub.pridruzi(p["qr_id"], "napacna", "telefon1", "Telefon")[1], "qr_ne_obstaja")
        zeton, napaka = self.hub.pridruzi(p["qr_id"], p["secret"], "telefon1", "Telefon")
        self.assertIsNone(napaka)
        self.assertEqual(self.hub.naprava_zetona(zeton), ("telefon1", "Telefon"))
        # Koda velja enkrat.
        self.assertEqual(self.hub.pridruzi(p["qr_id"], p["secret"], "telefon2", "Drug")[1], "qr_ne_obstaja")

    def test_ugibanje_skrivnosti_je_omejeno(self):
        p = self._povabilo()
        for _ in range(link_hub_streznik.NAJVEC_POSKUSOV - 1):
            self.assertEqual(self.hub.pridruzi(p["qr_id"], "x", "telefon1", "T")[1], "qr_ne_obstaja")
        self.assertEqual(self.hub.pridruzi(p["qr_id"], "x", "telefon1", "T")[1], "prevec_poskusov")
        self.assertEqual(self.hub.pridruzi(p["qr_id"], p["secret"], "telefon1", "T")[1], "qr_ne_obstaja")

    def test_preklic_kode(self):
        p = self._povabilo()
        self.hub.obdelaj(self.tv, json.dumps({"id": "p2", "type": "pair.invite.cancel", "payload": {"qr_id": p["qr_id"]}}))
        self.assertEqual(self.hub.pridruzi(p["qr_id"], p["secret"], "telefon1", "T")[1], "qr_ne_obstaja")

    def test_koda_potece(self):
        ura = [500.0]
        hub = link_hub_streznik.Hub(odtis="ef" * 32, ura=lambda: ura[0])
        qr_id, skrivnost = hub.ustvari_pridruzitev()
        ura[0] += link_hub_streznik.PIN_VELJA_S + 1
        self.assertEqual(hub.pridruzi(qr_id, skrivnost, "telefon1", "T")[1], "qr_ne_obstaja")
