#!/usr/bin/env python3
"""Safeer OS za racunalnik - preobleka cez Linux Mint.

Isti Safeer OS kot na televizorju, le za racunalnik: celozaslonski domaci zaslon z levim menijem
(Domov, Programi, Datoteke, Naprave, Nastavitve), ki pokaze VSE, kar je ze na racunalniku -
programe iz menija, uporabnikove mape, nastavitve Minta - in doda Safeerjeve reci (Safeer Link,
spletne aplikacije, iskanje po vsem hkrati).

Pod njim ostane Linux Mint: programi se odpirajo v svojih oknih, nastavitve so Mintove
(cinnamon-settings, Upravitelj posodobitev ...), zato Safeer OS nicesar ne podvaja in nicesar
ne pokvari. Ko ga uporabnik zapre, je tam njegovo obicajno namizje.

Zagon:
  safeer_os.py                 celozaslonsko (privzeto)
  safeer_os.py --okno          v oknu (za preizkus ob drugem delu)
  safeer_os.py --posnetek P    izrise stran, shrani posnetek v P (PNG) in konca (preverjanje)

Prvi zagon: ce racunalnik se ni v Safeer Linku in uporabnik ni izbral »Nadaljuj brez povezave
naprav«, Safeer OS odpre prijavno okno Safeer Control (QR / 6-mestna koda / brez povezave).
Naprave lahko uporabnik kadarkoli poveze v razdelku Naprave.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from typing import Optional

KOREN = os.path.dirname(os.path.abspath(__file__))
if KOREN not in sys.path:
    sys.path.insert(0, KOREN)

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit2  # noqa: E402

from core import os_datoteke, os_programi, os_sistem  # noqa: E402

APP_ID = "io.github.memelandfaner.SafeerOS"
RAZLICICA = "0.1.0"
CONTROL_NASTAVITVE = os.path.expanduser("~/.config/safeer-control/link.json")
BRSKALNIK_NASTAVITVE = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                                    "safeer-mint", "settings.json")
ISKALNIKI = {"google": "https://www.google.com/search?q=", "duckduckgo": "https://duckduckgo.com/?q=",
             "brave": "https://search.brave.com/search?q=", "startpage": "https://www.startpage.com/do/search?q=",
             "bing": "https://www.bing.com/search?q=", "ecosia": "https://www.ecosia.org/search?q="}

MOST_JS = r"""
(function () {
  var cakajo = {}, stevec = 0;
  window.__safeerOsOdgovor = function (id, ok, podatki) {
    var c = cakajo[id]; if (!c) return; delete cakajo[id];
    if (ok) c.res(podatki); else c.rej(podatki);
  };
  window.SafeerOS = {
    klic: function (metoda, argumenti) {
      return new Promise(function (res, rej) {
        var id = ++stevec; cakajo[id] = { res: res, rej: rej };
        try {
          window.webkit.messageHandlers.safeerOs.postMessage(JSON.stringify({ id: id, m: metoda, a: argumenti || [] }));
        } catch (e) { delete cakajo[id]; rej(String(e)); }
      });
    }
  };
})();
"""


def _jezik() -> str:
    """Jezik vmesnika: nastavitev Safeer Browserja, sicer jezik seje; podprti sl/en/de/es/fr/it."""
    try:
        with open(BRSKALNIK_NASTAVITVE, encoding="utf-8") as f:
            v = (json.load(f) or {}).get("ui_language")
        if v:
            return str(v)[:2]
    except Exception:
        pass
    lang = (os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "en")[:2].lower()
    return lang if lang in ("sl", "en", "de", "es", "fr", "it") else "en"


def _ime_sistema() -> str:
    """Ime sistema iz /etc/os-release (npr. »Linux Mint 22.3«) - kar je res namesceno."""
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for vrstica in f:
                if vrstica.startswith("PRETTY_NAME="):
                    return vrstica.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return "Linux"


def _iskalnik() -> str:
    try:
        with open(BRSKALNIK_NASTAVITVE, encoding="utf-8") as f:
            ime = (json.load(f) or {}).get("search_engine") or "duckduckgo"
    except Exception:
        ime = "duckduckgo"
    return ISKALNIKI.get(ime, ISKALNIKI["duckduckgo"])


def stanje_povezave() -> dict:
    """Ali je racunalnik (Safeer Control) v Safeer Linku: povezan / brez (izbral) / nov."""
    try:
        with open(CONTROL_NASTAVITVE, encoding="utf-8") as f:
            p = json.load(f) or {}
    except Exception:
        p = {}
    seznanjen = bool(p.get("control_token")) and bool(p.get("hub_fp"))
    v_krogu = False
    try:
        from core import link_hub, link_krog
        v_krogu = bool(link_krog.lahko_s_podpisom(link_hub.id_naprave() + "-control"))
    except Exception:
        pass
    if seznanjen or v_krogu:
        stanje = "povezan"
    elif p.get("brez_povezave"):
        stanje = "brez"
    else:
        stanje = "nov"
    return {"stanje": stanje, "control": bool(_ukaz_controla())}


def _ukaz_controla() -> Optional[list]:
    from shutil import which
    pot = which("safeer-control")
    if pot:
        return [pot]
    skripta = os.path.join(KOREN, "safeer_control.py")
    if os.path.isfile(skripta):
        return [sys.executable, skripta]
    return None


class SafeerOS(Gtk.Application):
    def __init__(self, v_oknu: bool = False, posnetek: str = "") -> None:
        zastavice = Gio.ApplicationFlags.NON_UNIQUE if posnetek else Gio.ApplicationFlags.FLAGS_NONE
        super().__init__(application_id=APP_ID, flags=zastavice)
        self.v_oknu = v_oknu
        self.posnetek = posnetek
        self.shramba = os_programi.Shramba()
        self.programi = os_programi.Programi(self.shramba)
        self.okno: Optional[Gtk.ApplicationWindow] = None
        self.pogled: Optional[WebKit2.WebView] = None
        self._ikone: dict = {}
        self._wnck = None
        self._prvic = True

    # ------------------------------------------------------------------ okno
    def do_activate(self) -> None:
        if self.okno is not None:
            self.okno.deiconify()
            self.okno.present()
            self._dogodek("fokus", None)
            return
        self._ustvari_okno()
        if self._prvic and not self.posnetek:
            self._prvic = False
            if stanje_povezave()["stanje"] == "nov":
                # Prvi zagon brez Safeer Linka: prijavno okno (QR / koda / brez povezave naprav).
                GLib.timeout_add(1200, lambda: (self._odpri_control(), False)[1])

    def _ustvari_okno(self) -> None:
        upravitelj = WebKit2.UserContentManager()
        upravitelj.register_script_message_handler("safeerOs")
        upravitelj.connect("script-message-received::safeerOs", self._na_sporocilo)
        upravitelj.add_script(WebKit2.UserScript(
            MOST_JS, WebKit2.UserContentInjectedFrames.TOP_FRAME,
            WebKit2.UserScriptInjectionTime.START, None, None))
        pogled = WebKit2.WebView.new_with_user_content_manager(upravitelj)
        n = pogled.get_settings()
        n.set_property("enable-developer-extras", bool(os.environ.get("SAFEER_OS_RAZVOJ")))
        n.set_property("enable-webgl", False)
        try:
            n.set_property("default-font-size", 16)
            n.set_property("minimum-font-size", 0)
        except Exception:
            pass
        barva = Gdk.RGBA()
        barva.parse("#090d15")
        pogled.set_background_color(barva)
        pogled.connect("decide-policy", self._na_politiko)
        pogled.connect("context-menu", lambda *a: True)   # brez »Reload / Inspect« v preobleki

        okno = Gtk.ApplicationWindow(application=self, title="Safeer OS")
        okno.set_wmclass("safeer-os", "Safeer OS")
        okno.set_icon_name("safeer-browser")
        zaslon = None
        try:
            zaslon = Gdk.Display.get_default().get_primary_monitor() or Gdk.Display.get_default().get_monitor(0)
        except Exception:
            pass
        if self.posnetek and os.environ.get("SAFEER_OS_OKNO"):
            sirina, visina = (int(x) for x in os.environ["SAFEER_OS_OKNO"].split("x"))
            okno.set_default_size(sirina, visina)
        elif self.v_oknu or not self.shramba.get("celozaslonsko", True):
            g = zaslon.get_workarea() if zaslon else None
            okno.set_default_size(min(1440, int(g.width * 0.9)) if g else 1280,
                                  min(900, int(g.height * 0.9)) if g else 800)
            okno.set_position(Gtk.WindowPosition.CENTER)
        else:
            okno.set_decorated(False)
            okno.fullscreen()
        okno.add(pogled)
        okno.connect("key-press-event", self._na_tipko)
        okno.connect("focus-in-event", lambda *a: (self._dogodek("fokus", None), False)[1])
        okno.connect("destroy", lambda *a: self.quit())
        self.okno, self.pogled = okno, pogled

        self._koren_strani = "file://" + os.path.join(KOREN, "assets", "os")
        pogled.load_uri(self._koren_strani + "/index.html")
        if self.posnetek:
            pogled.connect("load-changed", self._za_posnetek)
        okno.show_all()
        GLib.timeout_add_seconds(10, self._periodicno)

    def _na_politiko(self, _pogled, odlocitev, vrsta) -> bool:
        """Pogled sme prikazati samo stran Safeer OS (most ne sme k tuji strani)."""
        try:
            if vrsta not in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,
                             WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
                return False
            naslov = odlocitev.get_navigation_action().get_request().get_uri() or ""
            if naslov.startswith(self._koren_strani + "/"):
                return False
            odlocitev.ignore()
            if naslov.startswith(("http://", "https://")):
                self._splet(naslov)
            return True
        except Exception:
            odlocitev.ignore()
            return True

    def _na_tipko(self, _okno, dogodek) -> bool:
        # F11: celozaslonsko / v oknu (obicajna bliznjica, deluje tudi, ko se kaj zatakne).
        if dogodek.keyval == Gdk.KEY_F11:
            self._celozaslonsko(not self.shramba.get("celozaslonsko", True))
            return True
        return False

    def _celozaslonsko(self, vklop: bool) -> bool:
        self.shramba.set("celozaslonsko", bool(vklop))
        if self.okno is None:
            return vklop
        if vklop:
            self.okno.set_decorated(False)
            self.okno.fullscreen()
        else:
            self.okno.unfullscreen()
            self.okno.set_decorated(True)
        return vklop

    def _periodicno(self) -> bool:
        if self.okno is None:
            return False
        if self.okno.is_active():
            threading.Thread(target=lambda: self._dogodek("stanje", os_sistem.stanje()), daemon=True).start()
        return True

    # ------------------------------------------------------------------ posnetek (preverjanje)
    def _za_posnetek(self, pogled, dogodek) -> None:
        if dogodek != WebKit2.LoadEvent.FINISHED:
            return
        razdelek = os.environ.get("SAFEER_OS_RAZDELEK", "")
        if razdelek:
            GLib.timeout_add(1500, lambda: (self._js("window.safeerOsPojdi && safeerOsPojdi(%s)" % json.dumps(razdelek)), False)[1])
        def velikost():
            self.pogled.evaluate_javascript("innerWidth + 'x' + innerHeight + ' @' + devicePixelRatio", -1, None, None, None,
                                            lambda p, r: print("pogled:", p.evaluate_javascript_finish(r).to_string()))
            return False
        GLib.timeout_add(3500, velikost)
        GLib.timeout_add(4000, self._naredi_posnetek)

    def _naredi_posnetek(self) -> bool:
        def konec(pogled, rezultat):
            try:
                povrsina = pogled.get_snapshot_finish(rezultat)
                povrsina.write_to_png(self.posnetek)
                print("posnetek:", self.posnetek)
            except Exception as e:  # noqa: BLE001
                print("posnetek ni uspel:", e)
            self.quit()
        self.pogled.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, konec)
        return False

    # ------------------------------------------------------------------ most
    def _js(self, koda: str) -> None:
        if self.pogled is not None:
            try:
                self.pogled.run_javascript(koda, None, None, None)
            except Exception:
                pass

    def _odgovori(self, id_, ok: bool, podatki) -> None:
        def naredi():
            self._js("window.__safeerOsOdgovor(%d, %s, %s);" % (
                int(id_), "true" if ok else "false", json.dumps(podatki, ensure_ascii=True)))
            return False
        GLib.idle_add(naredi)

    def _dogodek(self, vrsta: str, podatki) -> None:
        def naredi():
            self._js("window.safeerOsDogodek && window.safeerOsDogodek(%s, %s);" % (
                json.dumps(vrsta), json.dumps(podatki, ensure_ascii=True)))
            return False
        GLib.idle_add(naredi)

    def _na_sporocilo(self, _upravitelj, rezultat) -> None:
        try:
            s = json.loads(rezultat.get_js_value().to_string())
            id_, metoda, a = int(s.get("id", 0)), str(s.get("m", "")), list(s.get("a") or [])
        except Exception:
            return
        # Na glavni niti (Gtk, ikone, okna):
        glavna = {
            "zacetek": self._zacetek,
            "programi": lambda: self.programi.seznam(self._ikona),
            "zazeni": lambda: self.programi.zazeni(str(a[0]) if a else "", self._zazeni_vnos),
            "pripni": lambda: self.programi.pripni(str(a[0]), bool(a[1]) if len(a) > 1 else True),
            "nedavne": self._nedavne,
            "odprtaOkna": self._odprta_okna,
            "aktivirajOkno": lambda: self._okno_dejanje(a[0] if a else 0, "aktiviraj"),
            "zapriOkno": lambda: self._okno_dejanje(a[0] if a else 0, "zapri"),
            "namizje": self._namizje,
            "celozaslonsko": lambda: self._celozaslonsko(bool(a[0]) if a else True),
            "control": lambda: self._odpri_control(),
            "shraniSpletne": lambda: self._shrani_spletne(a[0] if a else []),
        }
        # V ozadju (ukazi, ki lahko trajajo):
        ozadje = {
            "stanje": os_sistem.stanje,
            "glasnost": lambda: os_sistem.nastavi_glasnost(int(a[0])),
            "utisaj": os_sistem.preklopi_utisaj,
            "svetlost": lambda: os_sistem.nastavi_svetlost(int(a[0])),
            "nocna": lambda: os_sistem.nastavi_nocno_luc(bool(a[0])),
            "wifi": lambda: os_sistem.nastavi_wifi(bool(a[0])),
            "nastavitve": lambda: os_sistem.odpri_nastavitve(str(a[0]) if a else ""),
            "napajanje": lambda: os_sistem.napajanje(str(a[0]) if a else ""),
            "mapa": lambda: os_datoteke.preglej(str(a[0]) if a else "~"),
            "isciDatoteke": lambda: os_datoteke.isci(str(a[0]) if a else ""),
            "odpriDatoteko": lambda: os_datoteke.odpri(str(a[0]) if a else ""),
            "pokaziVMapi": lambda: os_datoteke.pokazi_v_mapi(str(a[0]) if a else ""),
            "splet": lambda: self._splet(str(a[0]) if a else ""),
            "iskanjeSplet": lambda: self._splet(_iskalnik() + GLib.uri_escape_string(str(a[0] if a else ""), None, False)),
            "povezava": stanje_povezave,
        }
        if metoda in glavna:
            try:
                self._odgovori(id_, True, glavna[metoda]())
            except Exception as e:  # noqa: BLE001
                print("[SafeerOS]", metoda, e)
                self._odgovori(id_, False, str(e))
        elif metoda in ozadje:
            def delo():
                try:
                    self._odgovori(id_, True, ozadje[metoda]())
                except Exception as e:  # noqa: BLE001
                    print("[SafeerOS]", metoda, e)
                    self._odgovori(id_, False, str(e))
            threading.Thread(target=delo, daemon=True).start()
        else:
            self._odgovori(id_, False, "neznano")

    # ------------------------------------------------------------------ dejanja
    def _zacetek(self) -> dict:
        ozadje = os_sistem.ozadje_namizja()
        return {
            "jezik": _jezik(),
            "ime": GLib.get_real_name() if GLib.get_real_name() not in ("", "Unknown") else GLib.get_user_name(),
            "racunalnik": socket.gethostname(),
            "ozadje": ("file://" + GLib.uri_escape_string(ozadje, "/", False)) if ozadje else "",
            "razpolozljivo": os_sistem.razpolozljivo(),
            "mape": os_datoteke.uporabniske_mape(),
            "celozaslonsko": bool(self.shramba.get("celozaslonsko", True)) and not self.v_oknu,
            "spletne": self.shramba.get("spletne", None),
            "razlicica": RAZLICICA,
            "sistem": _ime_sistema(),
            "povezava": stanje_povezave(),
        }

    def _shrani_spletne(self, seznam) -> list:
        """Spletne aplikacije na domacem zaslonu: samo ime in naslov http(s), najvec 24."""
        cisti = []
        for e in (seznam if isinstance(seznam, list) else [])[:24]:
            if not isinstance(e, dict):
                continue
            ime, url = str(e.get("ime", ""))[:40].strip(), str(e.get("url", ""))[:300].strip()
            if ime and url.startswith(("https://", "http://")):
                cisti.append({"ime": ime, "url": url})
        self.shramba.set("spletne", cisti)
        return cisti

    def _ikona(self, ime: str) -> str:
        if ime not in self._ikone:
            pot = os_programi.pot_ikone(ime)
            self._ikone[ime] = ("file://" + GLib.uri_escape_string(pot, "/", False)) if pot else ""
        return self._ikone[ime]

    def _zazeni_vnos(self, pot: str) -> bool:
        info = Gio.DesktopAppInfo.new_from_filename(pot)
        if info is None:
            return False
        kontekst = Gdk.Display.get_default().get_app_launch_context()
        kontekst.set_timestamp(Gtk.get_current_event_time() or Gdk.CURRENT_TIME)
        return bool(info.launch([], kontekst))

    def _nedavne(self) -> list:
        izhod = []
        try:
            for e in Gtk.RecentManager.get_default().get_items():
                if not e.exists() or not e.is_local():
                    continue
                pot = GLib.filename_from_uri(e.get_uri())[0]
                if os.path.isdir(pot):
                    continue
                cas = e.get_modified()          # GTK 3: int (time_t); novejsi: GLib.DateTime
                cas = cas.to_unix() if hasattr(cas, "to_unix") else int(cas or 0)
                try:
                    velikost = os.path.getsize(pot)
                except OSError:
                    velikost = 0
                izhod.append({"ime": e.get_display_name(), "pot": pot, "cas": cas, "spremenjeno": cas,
                              "velikost": velikost, "vrsta": os_datoteke.vrsta_datoteke(pot), "mapa": False})
        except Exception as e:  # noqa: BLE001
            print("[SafeerOS] nedavne:", e)
        izhod.sort(key=lambda d: -d["cas"])
        return izhod[:24]

    # --- odprta okna (Wnck: samo X11; na Waylandu seznama ni)
    def _zaslon_wnck(self):
        if self._wnck is None:
            try:
                gi.require_version("Wnck", "3.0")
                from gi.repository import Wnck
                Wnck.set_client_type(Wnck.ClientType.PAGER)
                self._wnck = Wnck.Screen.get_default()
            except Exception:
                self._wnck = False
        return self._wnck or None

    def _odprta_okna(self) -> list:
        zaslon = self._zaslon_wnck()
        if zaslon is None:
            return []
        try:
            from gi.repository import Wnck
            zaslon.force_update()
            moj = self.okno.get_window().get_xid() if self.okno and self.okno.get_window() else 0
            izhod = []
            for o in zaslon.get_windows_stacked() or []:
                if o.get_window_type() != Wnck.WindowType.NORMAL or o.is_skip_tasklist() or o.get_xid() == moj:
                    continue
                ikona = ""
                try:
                    pb = o.get_icon()
                    if pb is not None:
                        pot = os.path.join(os_programi.MAPA_IKON, "okno-%d.png" % o.get_xid())
                        os.makedirs(os_programi.MAPA_IKON, exist_ok=True)
                        pb.savev(pot, "png", [], [])
                        ikona = "file://" + pot + "?t=%d" % int(time.time())
                except Exception:
                    pass
                izhod.append({"id": o.get_xid(), "ime": o.get_name(), "program": (o.get_class_group_name() or ""),
                              "ikona": ikona, "pomanjsano": o.is_minimized()})
            izhod.reverse()      # najnovejse zgoraj
            return izhod
        except Exception as e:  # noqa: BLE001
            print("[SafeerOS] okna:", e)
            return []

    def _okno_dejanje(self, xid, dejanje: str) -> bool:
        zaslon = self._zaslon_wnck()
        if zaslon is None:
            return False
        cas = Gtk.get_current_event_time() or int(GLib.get_monotonic_time() / 1000)
        for o in zaslon.get_windows() or []:
            if o.get_xid() == int(xid):
                if dejanje == "zapri":
                    o.close(cas)
                else:
                    o.activate(cas)
                return True
        return False

    def _namizje(self) -> bool:
        """Umakne Safeer OS in pokaze Mintovo namizje (vrne se s klikom v meniju ali na plosci)."""
        if self.okno is not None:
            self.okno.iconify()
        return True

    def _splet(self, naslov: str) -> bool:
        if not naslov.startswith(("http://", "https://")):
            return False
        from shutil import which
        for ukaz in (["safeer-browser", naslov], ["safeer", naslov], ["xdg-open", naslov]):
            if which(ukaz[0]):
                try:
                    subprocess.Popen(ukaz, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                    return True
                except Exception:
                    continue
        return False

    def _odpri_control(self) -> bool:
        """Safeer Control: prijavno okno (QR / koda) ali seznam naprav, ce je racunalnik ze povezan."""
        ukaz = _ukaz_controla()
        if not ukaz:
            return False
        try:
            subprocess.Popen(ukaz, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True
        except Exception:
            return False


def main() -> int:
    if "--version" in sys.argv[1:]:
        print("Safeer OS", RAZLICICA)
        return 0
    posnetek = ""
    if "--posnetek" in sys.argv[1:]:
        i = sys.argv.index("--posnetek")
        posnetek = sys.argv[i + 1] if i + 1 < len(sys.argv) else "/tmp/safeer-os.png"
    app = SafeerOS(v_oknu="--okno" in sys.argv[1:], posnetek=posnetek)
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
