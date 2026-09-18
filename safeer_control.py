#!/usr/bin/env python3
"""Safeer Control — namizna aplikacija za upravljanje naprav prek Safeer Linka.

Brez brskalnika: Safeer Control ima Safeer Link vgrajen. Racunalnik se s 6-mestno kodo
poveze v domaci Safeer Link (na televizorju ali telefonu), potem ima uporabnik v tem oknu
daljinec za televizor (glas, tipke, aplikacije) in telefon, deljenje besedila, datotek in
zaslona - vse v domacem omrezju, brez oblaka in brez racuna.

Ista stran kot v brskalniku (assets/link/), isti Link (core/link_hub.py, core/safeer_link.py).
Kar potrebuje brskalnik (posiljanje odprte strani, zaznamki), stran v Controlu skrije.

Svoja identiteta in shramba: ~/.config/safeer-control/link.json. Ce je na tem racunalniku
Safeer Browser ze povezan v Safeer Link, Control tega ne podira - obe aplikaciji sta v Linku
vsaka s svojim imenom.

Datoteke za televizor: uporabnik izbere mape (stran Control ali pladenj), Safeer OS na
televizorju jih pregleduje in predvaja naravnost z racunalnika (core/link_datoteke.py). Brez
izbrane mape televizor ne vidi nic.

Tiho v ozadju: `safeer-control --ozadje` se poveze v Safeer Link brez okna in pusti ikono v
pladnju (Odpri, Zazeni ob prijavi, Koncaj). Ko je racunalnik enkrat seznanjen, se Control ob
prijavi zaganja sam (~/.config/autostart) - uporabnik ne zaganja nicesar; televizor in telefon
ga vidita, kadar je racunalnik prizgan. Zapiranje okna Control le skrije.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Optional

KOREN = os.path.dirname(os.path.abspath(__file__))
if KOREN not in sys.path:
    sys.path.insert(0, KOREN)

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gio, GLib, Gtk, WebKit2  # noqa: E402

from core import link_datoteke, link_hub, link_programi, link_tls, link_zaslon  # noqa: E402
from core.safeer_link import SafeerLink  # noqa: E402

APP_ID = "io.github.memelandfaner.SafeerControl"
NASTAVITVE_MAPA = os.path.expanduser("~/.config/safeer-control")
SAMOZAGON_POT = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "autostart", "safeer-control.desktop")

# Besedila pladnja v jezikih vmesnika (isti nabor kot Safeer Browser).
BESEDILA = {
    "sl": {"odpri": "Odpri Safeer Control", "samozagon": "Zaženi ob prijavi", "mape": "Mape za televizor …", "programi": "Programi za televizor", "ves_disk": "Ves računalnik za televizor", "zaslon": "Zaslon za televizor", "koncaj": "Končaj", "povezan": "Safeer Link: povezan", "ni": "Safeer Link: ni povezave"},
    "en": {"odpri": "Open Safeer Control", "samozagon": "Start at login", "mape": "Folders for the TV…", "programi": "Apps for the TV", "ves_disk": "Whole computer for the TV", "zaslon": "Screen for the TV", "koncaj": "Quit", "povezan": "Safeer Link: connected", "ni": "Safeer Link: not connected"},
    "de": {"odpri": "Safeer Control öffnen", "samozagon": "Beim Anmelden starten", "mape": "Ordner für den Fernseher …", "programi": "Programme für den Fernseher", "ves_disk": "Ganzer Computer für den Fernseher", "zaslon": "Bildschirm für den Fernseher", "koncaj": "Beenden", "povezan": "Safeer Link: verbunden", "ni": "Safeer Link: nicht verbunden"},
    "es": {"odpri": "Abrir Safeer Control", "samozagon": "Iniciar al iniciar sesión", "mape": "Carpetas para el televisor…", "programi": "Programas para el televisor", "ves_disk": "Todo el ordenador para el televisor", "zaslon": "Pantalla para el televisor", "koncaj": "Salir", "povezan": "Safeer Link: conectado", "ni": "Safeer Link: sin conexión"},
    "fr": {"odpri": "Ouvrir Safeer Control", "samozagon": "Lancer à la connexion", "mape": "Dossiers pour le téléviseur…", "programi": "Programmes pour le téléviseur", "ves_disk": "Tout l'ordinateur pour le téléviseur", "zaslon": "Écran pour le téléviseur", "koncaj": "Quitter", "povezan": "Safeer Link : connecté", "ni": "Safeer Link : non connecté"},
    "it": {"odpri": "Apri Safeer Control", "samozagon": "Avvia all’accesso", "mape": "Cartelle per il televisore…", "programi": "Programmi per il televisore", "ves_disk": "Tutto il computer per il televisore", "zaslon": "Schermo per il televisore", "koncaj": "Esci", "povezan": "Safeer Link: connesso", "ni": "Safeer Link: non connesso"},
}


def besedilo(jezik: Optional[str], kljuc: str) -> str:
    return BESEDILA.get((jezik or "en")[:2], BESEDILA["en"]).get(kljuc, BESEDILA["en"][kljuc])


def razlicica() -> str:
    try:
        with open(os.path.join(KOREN, "packaging", "VERSION_CONTROL"), encoding="utf-8") as d:
            return d.read().strip()
    except Exception:
        return ""


APP_VERSION = razlicica()


class Nastavitve:
    """Majhna shramba nastavitev Controla (jezik ipd.); isti vmesnik, kot ga Link pricakuje od brskalnika."""

    def __init__(self, pot: str) -> None:
        self.pot = pot
        self.podatki: dict = {}
        try:
            with open(pot, "r", encoding="utf-8") as d:
                self.podatki = json.load(d) or {}
        except Exception:
            self.podatki = {}

    def get(self, kljuc: str, privzeto=None):
        v = self.podatki.get(kljuc)
        if v is None and kljuc == "ui_language":
            # Jezik vmesnika: ce ima uporabnik na tem racunalniku Safeer Browser, govori Control v istem jeziku.
            v = _jezik_brskalnika()
        return v if v is not None else privzeto

    def set(self, kljuc: str, vrednost) -> None:
        self.podatki[kljuc] = vrednost
        try:
            os.makedirs(os.path.dirname(self.pot), exist_ok=True)
            zacasna = self.pot + ".tmp"
            with open(zacasna, "w", encoding="utf-8") as d:
                json.dump(self.podatki, d, ensure_ascii=False, indent=2)
            os.chmod(zacasna, 0o600)
            os.replace(zacasna, self.pot)
        except Exception:
            pass

    # Sinhronizacija zaznamkov je stvar brskalnika; Control je nima.
    def get_portals(self) -> list:
        return []

    def import_bookmarks_items(self, _postavke) -> tuple:
        return 0, 0


def _jezik_brskalnika() -> Optional[str]:
    pot = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "safeer-mint", "settings.json")
    try:
        with open(pot, "r", encoding="utf-8") as d:
            v = (json.load(d) or {}).get("ui_language")
        return str(v) if v else None
    except Exception:
        return None


def prevzemi_seznanitev_brskalnika(nastavitve: link_hub.Nastavitve, id_naprave: str, ime: str) -> bool:
    """Ce je Safeer Browser na tem racunalniku ze v Safeer Linku, Control vstopi brez nove kode.

    Brskalnikov zeton (ista datoteka istega uporabnika) Hubu dokaze, da smo isti racunalnik; Hub
    izda Controlu njegov lasten zeton (sorodna naprava, /cast/pair/sibling). Brez brskalnika ali
    s starim Hubom ostane obicajna pot s kodo. Vrne True, ce je seznanitev zdaj prevzeta.
    """
    if nastavitve.get("control_token") and nastavitve.get("hub_fp"):
        return False  # Control je ze seznanjen sam
    pot = os.path.join(link_hub.NASTAVITVE_MAPA, "link.json")
    try:
        with open(pot, "r", encoding="utf-8") as d:
            brskalnik = json.load(d) or {}
    except Exception:
        return False
    kandidati = []
    hub, zeton, odtis = brskalnik.get("hub_url"), brskalnik.get("control_token"), brskalnik.get("hub_fp")
    if hub and zeton and odtis:
        kandidati.append((str(hub), str(zeton), str(odtis)))
    seznanitve = brskalnik.get("seznanitve")
    if isinstance(seznanitve, dict):
        for fp, z in seznanitve.items():
            if isinstance(z, dict) and z.get("token") and z.get("hub_url") and (str(z["hub_url"]), str(z["token"]), str(fp)) not in kandidati:
                kandidati.append((str(z["hub_url"]), str(z["token"]), str(fp)))
    uspelo = False
    seznanitve_controla = nastavitve.get("seznanitve") if isinstance(nastavitve.get("seznanitve"), dict) else {}
    for hub, zeton, odtis in kandidati:
        if not hub.startswith("wss://"):
            continue  # zeton gre samo po TLS
        try:
            koda, odgovor, _ = link_tls.zahteva(link_hub._osnova(hub) + "/cast/pair/sibling",
                                                {"device_id": id_naprave, "name": ime}, zeton, 4.0, pripeti=odtis)
        except Exception:
            continue
        nov = odgovor.get("token") if isinstance(odgovor, dict) else None
        if koda != 200 or not nov:
            continue
        seznanitve_controla[odtis] = {"token": str(nov), "hub_url": hub}
        if not uspelo:
            nastavitve.podatki["hub_url"] = hub
            nastavitve.podatki["control_token"] = str(nov)
            nastavitve.podatki["hub_fp"] = odtis
            uspelo = True
    if uspelo:
        nastavitve.podatki["seznanitve"] = seznanitve_controla
        nastavitve.shrani()
    return uspelo


def identiteta() -> tuple:
    """Control ima v Linku svoje ime in id, da ne trka z brskalnikom na istem racunalniku."""
    ime = link_hub._ime_naprave().split(".")[0]
    return link_hub.id_naprave() + "-control", "Safeer Control (" + ime + ")"


class Samozagon:
    """Zagon ob prijavi: vnos v ~/.config/autostart (XDG), ki pozene `safeer-control --ozadje`."""

    @staticmethod
    def je_vklopljen() -> bool:
        try:
            with open(SAMOZAGON_POT, "r", encoding="utf-8") as d:
                v = d.read()
            return "safeer-control" in v and "X-GNOME-Autostart-enabled=false" not in v and "Hidden=true" not in v
        except Exception:
            return False

    @staticmethod
    def nastavi(vklopljen: bool) -> None:
        try:
            if not vklopljen:
                if os.path.exists(SAMOZAGON_POT):
                    os.remove(SAMOZAGON_POT)
                return
            os.makedirs(os.path.dirname(SAMOZAGON_POT), exist_ok=True)
            ukaz = "safeer-control --ozadje"
            if not shutil_which("safeer-control"):
                ukaz = f'"{sys.executable}" "{os.path.abspath(__file__)}" --ozadje'
            with open(SAMOZAGON_POT, "w", encoding="utf-8") as d:
                d.write("[Desktop Entry]\nType=Application\nName=Safeer Control\n"
                        "Comment=Safeer Link v ozadju (daljinec, deljenje) / Safeer Link in the background\n"
                        f"Exec={ukaz}\nIcon=safeer-control\nTerminal=false\nNoDisplay=true\n"
                        "X-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=8\n")
        except Exception as e:  # noqa: BLE001
            print(f"[SafeerControl] Samozagona ni bilo mogoče nastaviti: {e}")


def shutil_which(ime: str) -> Optional[str]:
    import shutil
    return shutil.which(ime)


class Pladenj:
    """Ikona v pladnju: XApp.StatusIcon (Linux Mint/Cinnamon), sicer Gtk.StatusIcon."""

    def __init__(self, app: "SafeerControl") -> None:
        self.app = app
        self.jezik = app.nastavitve.get("ui_language")
        self.meni = Gtk.Menu()
        self.odpri = Gtk.MenuItem(label=besedilo(self.jezik, "odpri"))
        self.odpri.connect("activate", lambda *_a: app.pokazi_okno())
        self.samozagon = Gtk.CheckMenuItem(label=besedilo(self.jezik, "samozagon"))
        self.samozagon.set_active(Samozagon.je_vklopljen())
        self._preklop_id = self.samozagon.connect("toggled", self._preklop)
        self.mape = Gtk.MenuItem(label=besedilo(self.jezik, "mape"))
        self.mape.connect("activate", lambda *_a: app.izberi_mape())
        # Programi za televizor: privzeto izklopljeno; uporabnik vklopi tu in kadarkoli izklopi.
        self.programi = Gtk.CheckMenuItem(label=besedilo(self.jezik, "programi"))
        self.programi.set_active(bool(app.programi.vklopljeno))
        self._programi_id = self.programi.connect("toggled", self._preklop_programi)
        # Brskanje po celem racunalniku: privzeto izklopljeno. Vklopljeno pomeni, da televizor
        # vidi domaco mapo in koren diska, ne le izbranih map - zato je locena, zavestna izbira.
        self.ves_disk = Gtk.CheckMenuItem(label=besedilo(self.jezik, "ves_disk"))
        self.ves_disk.set_active(bool(app.datoteke.mape.ves_disk))
        self._ves_disk_id = self.ves_disk.connect("toggled", self._preklop_ves_disk)
        # Zaslon racunalnika na televizorju: privzeto izklopljeno, vklopi ga uporabnik tu.
        self.zaslon = Gtk.CheckMenuItem(label=besedilo(self.jezik, "zaslon"))
        self.zaslon.set_active(bool(app.zaslon.vklopljeno))
        self._zaslon_id = self.zaslon.connect("toggled", self._preklop_zaslon)
        self.koncaj = Gtk.MenuItem(label=besedilo(self.jezik, "koncaj"))
        self.koncaj.connect("activate", lambda *_a: app.koncaj())
        for m in (self.odpri, self.mape, self.ves_disk, self.programi, self.zaslon, Gtk.SeparatorMenuItem(), self.samozagon,
                  Gtk.SeparatorMenuItem(), self.koncaj):
            self.meni.append(m)
        self.meni.show_all()
        self.ikona = None
        self.xapp = None
        ikona = "safeer-control"
        try:
            if not Gtk.IconTheme.get_default().has_icon(ikona):
                ikona = os.path.join(KOREN, "assets", "icon.png")  # zagon iz izvorne kode brez namescene teme
        except Exception:
            pass
        try:
            gi.require_version("XApp", "1.0")
            from gi.repository import XApp  # noqa: WPS433
            self.xapp = XApp.StatusIcon()
            self.xapp.set_icon_name(ikona)
            self.xapp.set_name("safeer-control")
            self.xapp.set_secondary_menu(self.meni)
            self.xapp.connect("activate", lambda *_a: app.pokazi_okno())
        except Exception:
            self.ikona = Gtk.StatusIcon()
            if os.path.isabs(ikona):
                self.ikona.set_from_file(ikona)
            else:
                self.ikona.set_from_icon_name(ikona)
            self.ikona.set_title("Safeer Control")
            self.ikona.connect("activate", lambda *_a: app.pokazi_okno())
            self.ikona.connect("popup-menu", lambda ikona, gumb, cas: self.meni.popup(None, None, Gtk.StatusIcon.position_menu, ikona, gumb, cas))
        self.stanje(False)

    def stanje(self, povezan: bool) -> None:
        napis = besedilo(self.jezik, "povezan" if povezan else "ni")
        try:
            if self.xapp is not None:
                self.xapp.set_tooltip_text(napis)
            elif self.ikona is not None:
                self.ikona.set_tooltip_text(napis)
        except Exception:
            pass

    def _preklop_programi(self, postavka: Gtk.CheckMenuItem) -> None:
        self.app.nastavi_programe(bool(postavka.get_active()))

    def _preklop_ves_disk(self, postavka: Gtk.CheckMenuItem) -> None:
        self.app.nastavi_ves_disk(bool(postavka.get_active()))

    def _preklop_zaslon(self, postavka: Gtk.CheckMenuItem) -> None:
        self.app.nastavi_zaslon(bool(postavka.get_active()))

    def _preklop(self, element) -> None:
        self.app.nastavi_samozagon(element.get_active())

    def osvezi_samozagon(self) -> None:
        self.samozagon.handler_block(self._preklop_id)
        self.samozagon.set_active(Samozagon.je_vklopljen())
        self.samozagon.handler_unblock(self._preklop_id)


class SafeerControl(Gtk.Application):
    def __init__(self, ozadje: bool = False) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.link: Optional[SafeerLink] = None
        self.nastavitve = Nastavitve(os.path.join(NASTAVITVE_MAPA, "control.json"))
        self.web_context = WebKit2.WebContext.get_default()
        self.gledalec: Optional[Gtk.Window] = None
        # --ozadje: brez okna, z ikono v pladnju; okno se odpre iz pladnja ali ob ponovnem zagonu iz menija.
        self.ozadje = ozadje
        self.pladenj: Optional[Pladenj] = None
        self._prva_aktivacija = True
        # Deljene mape za televizor; seznam poti je v control.json ("deljene_mape").
        mape = self.nastavitve.get("deljene_mape")
        self.datoteke = link_datoteke.Datoteke(mape if isinstance(mape, list) else [],
                                              ves_disk=bool(self.nastavitve.get("ves_disk_za_tv", False)))
        self.datoteke.ob_spremembi = lambda poti: self.nastavitve.set("deljene_mape", poti)
        # Programi racunalnika za televizor; privzeto izklopljeno ("programi_za_tv" v control.json).
        self.programi = link_programi.Programi(bool(self.nastavitve.get("programi_za_tv", False)))
        self.programi.ob_spremembi = lambda vklopljeno: self.nastavitve.set("programi_za_tv", bool(vklopljeno))
        # Zaslon racunalnika na televizorju; privzeto izklopljeno ("zaslon_za_tv" v control.json).
        self.zaslon = link_zaslon.Zaslon(vklopljeno=bool(self.nastavitve.get("zaslon_za_tv", False)))
        self.zaslon.ob_spremembi = lambda vklopljeno: self.nastavitve.set("zaslon_za_tv", bool(vklopljeno))

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        if self.ozadje:
            self.hold()  # brez okna bi se GApplication koncal; ikona v pladnju ga drzi

    def _pripravi_link(self) -> None:
        nastavitve_linka = link_hub.Nastavitve(os.path.join(NASTAVITVE_MAPA, "link.json"))
        id_naprave, ime = identiteta()
        try:
            if prevzemi_seznanitev_brskalnika(nastavitve_linka, id_naprave, ime):
                print("[SafeerControl] Seznanitev prevzeta od Safeer Browserja (brez kode).")
        except Exception as e:  # noqa: BLE001
            print(f"[SafeerControl] Seznanitve brskalnika ni bilo mogoče prevzeti: {e}")
        self.link = SafeerLink(
            None, self.nastavitve,
            trenutna_stran=lambda: {},
            odpri_naslov=self.odpri_naslov,
            koren_programa=KOREN,
            dovoli_potrdilo=self.dovoli_potrdilo,
            nastavitve=nastavitve_linka,
            identiteta=(id_naprave, ime),
            control=True,
            ob_zaprtju=self.ob_zaprtju_okna,
        )
        self.link.ob_povezavi = self._na_povezavo
        self.link.datoteke = self.datoteke
        self.link.programi = self.programi
        self.link.zaslon = self.zaslon

    def nastavi_zaslon(self, vklopljeno: bool) -> None:
        """Televizor sme (ali ne sme vec) videti zaslon tega racunalnika. Izklop takoj konca sejo;
        zmoznost `desktop` se javi ali odpade ob naslednji povezavi."""
        self.zaslon.nastavi(vklopljeno)
        if self.link is not None:
            try:
                self.link.povezi_v_ozadju()
            except Exception:
                pass

    def nastavi_ves_disk(self, vklopljeno: bool) -> None:
        """Televizor sme (ali ne sme vec) brskati po celem racunalniku, ne le po izbranih mapah.
        Velja takoj; nastavitev se zapomni ("ves_disk_za_tv" v control.json)."""
        self.datoteke.nastavi_ves_disk(vklopljeno)
        self.nastavitve.set("ves_disk_za_tv", bool(vklopljeno))

    def nastavi_programe(self, vklopljeno: bool) -> None:
        """Televizor sme (ali ne sme vec) videti programe tega racunalnika. Sprememba velja takoj:
        ob naslednji povezavi se zmoznost `apps` javi ali odpade."""
        self.programi.nastavi(bool(vklopljeno))
        if self.link is not None:
            try:
                self.link.povezi_v_ozadju()   # zmoznost `apps` se javi (ali odpade) ob novi povezavi
            except Exception:
                pass

    def izberi_mape(self) -> None:
        """Izbira map za televizor iz pladnja (isti pogovor kot na strani Control)."""
        if self.link is None:
            self._pripravi_link()
        self.link.dodaj_deljeno_mapo()

    def _na_povezavo(self, povezan: bool) -> None:
        if self.pladenj is not None:
            GLib.idle_add(lambda: (self.pladenj.stanje(povezan), False)[1])
        # Prvic seznanjen racunalnik: od zdaj naprej se Control zaganja ob prijavi, da ga naprave vidijo.
        if povezan and not self.nastavitve.get("samozagon_nastavljen"):
            self.nastavitve.set("samozagon_nastavljen", True)
            if self.nastavitve.get("samozagon", True):
                Samozagon.nastavi(True)
                if self.pladenj is not None:
                    GLib.idle_add(lambda: (self.pladenj.osvezi_samozagon(), False)[1])

    def nastavi_samozagon(self, vklopljen: bool) -> None:
        self.nastavitve.set("samozagon", bool(vklopljen))
        self.nastavitve.set("samozagon_nastavljen", True)
        Samozagon.nastavi(bool(vklopljen))

    def ob_zaprtju_okna(self) -> None:
        # Z ikono v pladnju zapiranje okna Control samo skrije; Link tece naprej.
        if self.pladenj is None:
            self.quit()

    def koncaj(self) -> None:
        try:
            if self.link is not None and self.link.povezava is not None:
                self.link.povezava.zapri()
        except Exception:
            pass
        try:
            self.datoteke.ustavi()
        except Exception:
            pass
        self.quit()

    def pokazi_okno(self) -> None:
        if self.link is None:
            self._pripravi_link()
        if self.link.okno is not None:
            self.link.okno.present()
            return
        self.link.pokazi()
        if self.link.okno is not None:
            self.add_window(self.link.okno)

    def do_activate(self) -> None:
        if self.ozadje and self._prva_aktivacija:
            self._prva_aktivacija = False
            if self.link is None:
                self._pripravi_link()
            self.pladenj = Pladenj(self)
            self.link.povezi_v_ozadju()
            return
        self._prva_aktivacija = False
        self.pokazi_okno()

    # ------------------------------------------------------------------
    # Odpiranje naslovov: gledalec zaslona s Huba v svojem oknu, vse drugo v sistemskem brskalniku
    # ------------------------------------------------------------------

    def dovoli_potrdilo(self, pem: str, gostitelj: str) -> None:
        try:
            potrdilo = Gio.TlsCertificate.new_from_pem(pem, -1)
            self.web_context.allow_tls_certificate_for_host(potrdilo, gostitelj)
        except Exception as e:  # noqa: BLE001
            print(f"[SafeerControl] Potrdila Huba ni bilo mogoče dovoliti: {e}")

    def _je_s_huba(self, url: str) -> bool:
        try:
            hub = self.link._hub() if self.link is not None else ""
            if not hub:
                return False
            from urllib.parse import urlparse
            return urlparse(url).hostname == urlparse(link_hub._osnova(hub)).hostname
        except Exception:
            return False

    def odpri_naslov(self, url: str) -> None:
        cist = (url or "").strip()
        if not (cist.startswith("http://") or cist.startswith("https://")):
            return
        if self._je_s_huba(cist):
            self._odpri_gledalca(cist)
            return
        # Prejete strani in povezave odpre brskalnik, ki ga uporabnik ze ima (ce je to Safeer, toliko bolje).
        try:
            Gio.AppInfo.launch_default_for_uri(cist, None)
        except Exception:
            try:
                subprocess.Popen(["xdg-open", cist])
            except Exception as e:  # noqa: BLE001
                print(f"[SafeerControl] Naslova ni bilo mogoče odpreti: {e}")

    def _odpri_gledalca(self, url: str) -> None:
        """Deljen zaslon druge naprave: stran gledalca s Huba v svojem oknu Controla."""
        if self.gledalec is None:
            pogled = WebKit2.WebView.new_with_context(self.web_context)
            nastavitve = pogled.get_settings()
            nastavitve.set_property("enable-developer-extras", False)
            okno = Gtk.Window(title="Safeer Control — zaslon")
            okno.set_default_size(960, 600)
            okno.add(pogled)

            def zaprto(*_a):
                self.gledalec = None
            okno.connect("destroy", zaprto)
            self.add_window(okno)
            self.gledalec = okno
            okno.show_all()
        pogled = self.gledalec.get_child()
        pogled.load_uri(url)
        self.gledalec.present()


def main() -> int:
    if "--version" in sys.argv[1:]:
        print(f"Safeer Control {APP_VERSION}")
        return 0
    ozadje = "--ozadje" in sys.argv[1:]
    argv = [a for a in sys.argv if a != "--ozadje"]
    GLib.set_prgname("safeer-control")
    GLib.set_application_name("Safeer Control")
    app = SafeerControl(ozadje=ozadje)
    return app.run(argv)


if __name__ == "__main__":
    sys.exit(main())
