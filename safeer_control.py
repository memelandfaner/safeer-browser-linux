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

from core import link_hub  # noqa: E402
from core.safeer_link import SafeerLink  # noqa: E402

APP_ID = "io.github.memelandfaner.SafeerControl"
NASTAVITVE_MAPA = os.path.expanduser("~/.config/safeer-control")


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


def identiteta() -> tuple:
    """Control ima v Linku svoje ime in id, da ne trka z brskalnikom na istem racunalniku."""
    ime = link_hub._ime_naprave().split(".")[0]
    return link_hub.id_naprave() + "-control", "Safeer Control (" + ime + ")"


class SafeerControl(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.link: Optional[SafeerLink] = None
        self.nastavitve = Nastavitve(os.path.join(NASTAVITVE_MAPA, "control.json"))
        self.web_context = WebKit2.WebContext.get_default()
        self.gledalec: Optional[Gtk.Window] = None

    def do_activate(self) -> None:
        if self.link is not None and self.link.okno is not None:
            self.link.okno.present()
            return
        if self.link is None:
            self.link = SafeerLink(
                None, self.nastavitve,
                trenutna_stran=lambda: {},
                odpri_naslov=self.odpri_naslov,
                koren_programa=KOREN,
                dovoli_potrdilo=self.dovoli_potrdilo,
                nastavitve=link_hub.Nastavitve(os.path.join(NASTAVITVE_MAPA, "link.json")),
                identiteta=identiteta(),
                control=True,
                ob_zaprtju=self.quit,
            )
        self.link.pokazi()
        if self.link.okno is not None:
            self.add_window(self.link.okno)

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
    GLib.set_prgname("safeer-control")
    GLib.set_application_name("Safeer Control")
    app = SafeerControl()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
