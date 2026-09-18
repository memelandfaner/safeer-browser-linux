"""Programi racunalnika za televizor (Safeer OS) prek Safeer Linka.

Uporabnik na racunalniku enkrat dovoli, da televizor vidi njegove programe (privzeto NE).
Takrat Control prebere namizne vnose XDG (`.desktop`: sistemski, uporabnikovi, Flatpak, Snap)
in televizorju poslje samo to, kar potrebuje za ploscico: oznako, ime, opis in ikono.

Televizor nikoli ne poslje ukaza ali poti - poslje samo **oznako** s tega seznama
(`app:<ime datoteke>.desktop`). Control jo poisce med svojimi vnosi in program zazene z
`gio launch` (ali `gtk-launch`), torej natanko tako, kot bi ga uporabnik kliknil v svojem meniju.
Lupine ni; kar ni na seznamu, se ne zazene.

Seznam programov je oseben podatek, zato gre samo napravam v Safeer Linku, ki jih je uporabnik
seznanil, in samo, dokler je moznost vklopljena.
"""

from __future__ import annotations

import base64
import configparser
import os
import shutil
import subprocess
from typing import Dict, List, Optional

NAJVEC = 200
IKONA_VELIKOST = 128
PREDPONA = "app:"

# Kategorije, ki na televizorju nimajo smisla (nastavitve sistema, konzolna orodja).
IZPUSTI_KATEGORIJE = {"Settings", "System", "ConsoleOnly", "Screensaver"}

# Skupine, po katerih televizor razvrsti programe (na sto programih je abecedni seznam prevec).
# Kljuc je nasa oznaka, vrednost so kategorije XDG, ki vanjo sodijo - isto delitev pozna uporabnik
# ze iz menija svojega namizja. Vrstni red steje: prva skupina, ki se ujame, obvelja, zato je
# Igra pred vsem drugim (igra z glasbo je se vedno igra).
SKUPINE = (
    ("igre", {"Game", "ActionGame", "AdventureGame", "ArcadeGame", "BoardGame", "BlocksGame",
              "CardGame", "KidsGame", "LogicGame", "RolePlaying", "Shooter", "Simulation",
              "SportsGame", "StrategyGame", "Emulator"}),
    ("programiranje", {"Development", "IDE", "Building", "Debugger", "GUIDesigner", "Profiling",
                       "RevisionControl", "Translation", "WebDevelopment"}),
    ("pisarna", {"Office", "WordProcessor", "Spreadsheet", "Presentation", "Calendar", "Finance",
                 "ContactManagement", "Database", "Dictionary", "Publishing",
                 "ProjectManagement", "TextEditor"}),
    ("predstavnost", {"AudioVideo", "Audio", "Video", "Graphics", "Photography", "Music",
                      "Player", "Recorder", "TV", "Midi", "Mixer", "Sequencer", "Tuner",
                      "RasterGraphics", "VectorGraphics", "3DGraphics", "Scanning", "OCR"}),
    ("splet", {"Network", "WebBrowser", "Email", "InstantMessaging", "Chat", "IRCClient",
               "FileTransfer", "News", "P2P", "RemoteAccess", "Telephony", "VideoConference",
               "WebSearch", "Feed"}),
    ("ucenje", {"Education", "Science", "Math", "NumericalAnalysis", "Astronomy", "Biology",
                "Chemistry", "ComputerScience", "Geography", "Geology", "History", "Languages",
                "Literature", "Music Education", "Physics", "Sports"}),
    ("orodja", {"Utility", "Accessibility", "Archiving", "Compression", "FileTools",
                "FileManager", "TerminalEmulator", "Monitor", "Security", "Printing",
                "PackageManager", "Calculator", "Clock", "Documentation"}),
)
#: Program brez uporabne kategorije: raje posteno "drugo" kot napacna skupina.
PRIVZETA_SKUPINA = "drugo"


def skupina(kategorije) -> str:
    """Nasa skupina za kategorije XDG enega namiznega vnosa."""
    nabor = set(kategorije or ())
    for oznaka, kategorije_skupine in SKUPINE:
        if nabor & kategorije_skupine:
            return oznaka
    return PRIVZETA_SKUPINA
# Vnosi, ki jih ne ponujamo, ker so del Safeerja samega ali brez okna.
IZPUSTI_OZNAKE = {"safeer-control.desktop"}


def _mape_vnosov() -> List[str]:
    doma = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    sistem = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    mape = [os.path.join(doma, "applications")]
    for d in sistem.split(":"):
        if d:
            mape.append(os.path.join(d, "applications"))
    # Flatpak in Snap nista vedno v XDG_DATA_DIRS (npr. pri zagonu iz seje brez profila).
    mape.append("/var/lib/flatpak/exports/share/applications")
    mape.append(os.path.join(doma, "flatpak/exports/share/applications"))
    mape.append("/var/lib/snapd/desktop/applications")
    vidne: List[str] = []
    for m in mape:
        p = os.path.realpath(m)
        if p not in vidne and os.path.isdir(p):
            vidne.append(p)
    return vidne


def _jezik() -> List[str]:
    """Kljuci imen po jeziku okolja: Name[sl_SI], Name[sl], Name."""
    lang = (os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "").split(".")[0]
    kljuci = []
    if lang:
        kljuci.append(lang)
        if "_" in lang:
            kljuci.append(lang.split("_")[0])
    return kljuci


def _vrednost(vnos: configparser.SectionProxy, kljuc: str) -> str:
    for jezik in _jezik():
        v = vnos.get(f"{kljuc}[{jezik}]")
        if v:
            return v
    return vnos.get(kljuc, "") or ""


class Programi:
    """Namizni vnosi racunalnika; brez dovoljenja uporabnika prazno."""

    def __init__(self, vklopljeno: bool = False, mape: Optional[List[str]] = None) -> None:
        self.vklopljeno = bool(vklopljeno)
        self._mape = list(mape) if mape is not None else None   # None = poisci sam (testi jih podajo)
        self.ob_spremembi = None          # klicatelj shrani nastavitev
        self._vnosi: Dict[str, dict] = {}  # oznaka -> {"pot", "ime", "opis", "ikona"}

    # ------------------------------------------------------------------ nastavitev
    def nastavi(self, vklopljeno: bool) -> None:
        self.vklopljeno = bool(vklopljeno)
        if not self.vklopljeno:
            self._vnosi = {}
        if self.ob_spremembi is not None:
            try:
                self.ob_spremembi(self.vklopljeno)
            except Exception:
                pass

    # ------------------------------------------------------------------ branje vnosov
    def _preberi(self) -> Dict[str, dict]:
        najdeni: Dict[str, dict] = {}
        # Dvakrat isti napis je na televizorju uganka, ne izbira: en program je pogosto namescen
        # dvakrat (sistemsko in kot Flatpak), vcasih pa imata dva razlicna programa isto ime
        # ("Archive Manager", "Help"). Obdrzimo prvega - mape beremo po vrsti, kot jih gleda
        # namizje, torej uporabnikove pred sistemskimi in te pred Flatpakom.
        videna_imena = set()
        for mapa in (self._mape if self._mape is not None else _mape_vnosov()):
            try:
                imena = sorted(os.listdir(mapa))
            except OSError:
                continue
            for ime in imena:
                if not ime.endswith(".desktop") or ime in IZPUSTI_OZNAKE or ime in najdeni:
                    continue
                pot = os.path.join(mapa, ime)
                podatki = self._vnos(pot)
                if podatki is not None:
                    kljuc_imena = podatki["ime"].strip().lower()
                    if kljuc_imena in videna_imena:
                        continue
                    videna_imena.add(kljuc_imena)
                    najdeni[ime] = podatki
                if len(najdeni) >= NAJVEC:
                    break
        return najdeni

    def _vnos(self, pot: str) -> Optional[dict]:
        razclen = configparser.RawConfigParser(strict=False)
        razclen.optionxform = str
        try:
            with open(pot, encoding="utf-8", errors="replace") as f:
                razclen.read_file(f)
        except Exception:
            return None
        if not razclen.has_section("Desktop Entry"):
            return None
        vnos = razclen["Desktop Entry"]
        if vnos.get("Type", "") != "Application":
            return None
        if (vnos.get("NoDisplay", "") or "").lower() == "true":
            return None
        if (vnos.get("Hidden", "") or "").lower() == "true":
            return None
        if (vnos.get("Terminal", "") or "").lower() == "true":
            return None          # konzolna orodja na televizorju nimajo smisla
        kategorije = {k for k in (vnos.get("Categories", "") or "").split(";") if k}
        if kategorije & IZPUSTI_KATEGORIJE:
            return None
        poskusi = vnos.get("TryExec", "") or ""
        if poskusi and not (os.path.isabs(poskusi) and os.access(poskusi, os.X_OK)) and not shutil.which(poskusi):
            return None          # program ni namescen
        ime = _vrednost(vnos, "Name").strip()
        if not ime:
            return None
        return {"pot": pot, "ime": ime, "opis": _vrednost(vnos, "Comment").strip(),
                "ikona": (vnos.get("Icon", "") or "").strip(), "skupina": skupina(kategorije)}

    # ------------------------------------------------------------------ za Safeer Link
    def seznam(self, z_ikonami: bool = True, od: int = 0, koliko: int = 0) -> dict:
        """Odgovor na `apps.list`: {"enabled", "items", "total", "offset"}.

        Ikone so PNG v base64 in seznam je lahko dolg (na tem racunalniku 84 programov), sporocila
        v Safeer Linku pa so omejena na 256 kB - cel seznam z ikonami je bil prevelik in je padel
        skozi. Zato ga posiljamo po kosih: [od, od+koliko). `koliko = 0` pomeni vse (za teste in
        odjemalce brez strani).
        """
        if not self.vklopljeno:
            return {"enabled": False, "items": [], "total": 0, "offset": 0}
        self._vnosi = self._preberi()
        urejeni = sorted(self._vnosi.items(), key=lambda p: p[1]["ime"].lower())
        skupaj = len(urejeni)
        od = max(0, int(od or 0))
        kos = urejeni[od:od + koliko] if koliko else urejeni[od:]
        vnosi = []
        for oznaka, v in kos:
            element = {"id": PREDPONA + oznaka, "name": v["ime"], "comment": v["opis"],
                       "group": v.get("skupina", PRIVZETA_SKUPINA)}
            if z_ikonami:
                ikona = self._ikona(v["ikona"])
                if ikona:
                    element["icon_png"] = ikona
            vnosi.append(element)
        return {"enabled": True, "items": vnosi, "total": skupaj, "offset": od}

    def zazeni(self, oznaka: str) -> bool:
        """Zazene program z oznako s seznama. Nic drugega; ukaza z omrezja ne izvajamo."""
        if not self.vklopljeno:
            return False
        ime = str(oznaka or "")
        if not ime.startswith(PREDPONA):
            return False
        ime = ime[len(PREDPONA):]
        if "/" in ime or not ime.endswith(".desktop"):
            return False
        if ime not in self._vnosi:
            self._vnosi = self._preberi()
        vnos = self._vnosi.get(ime)
        if vnos is None:
            return False
        pot = vnos["pot"]
        for ukaz in (["gio", "launch", pot], ["gtk-launch", ime]):
            if shutil.which(ukaz[0]) is None:
                continue
            try:
                subprocess.Popen(ukaz, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------ ikone
    def _ikona(self, ime: str) -> str:
        """Ikona kot PNG v base64 (televizor ne zna SVG). Prazno, ce je ne najdemo."""
        if not ime:
            return ""
        pot = ime if os.path.isabs(ime) and os.path.isfile(ime) else (self._iz_teme(ime) or self._poisci_ikono(ime))
        if not pot:
            return ""
        try:
            import gi
            gi.require_version("GdkPixbuf", "2.0")
            from gi.repository import GdkPixbuf
            slika = GdkPixbuf.Pixbuf.new_from_file_at_size(pot, IKONA_VELIKOST, IKONA_VELIKOST)
            ok, bajti = slika.save_to_bufferv("png", [], [])
            if ok:
                return base64.b64encode(bytes(bajti)).decode("ascii")
        except Exception:
            pass
        if pot.endswith(".png"):
            try:
                with open(pot, "rb") as f:
                    return base64.b64encode(f.read()).decode("ascii")
            except OSError:
                return ""
        return ""

    @staticmethod
    def _iz_teme(ime: str) -> str:
        """Ikono najprej poiscemo tako, kot jo namizje: prek teme ikon (GTK). Brez GTK (testi) prazno."""
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk
            tema = Gtk.IconTheme.get_default()
            if tema is None:
                return ""
            najdena = tema.lookup_icon(ime, IKONA_VELIKOST, 0)
            if najdena is not None:
                pot = najdena.get_filename() or ""
                if pot and os.path.isfile(pot):
                    return pot
        except Exception:
            pass
        return ""

    def _poisci_ikono(self, ime: str) -> str:
        doma = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        korenine = [os.path.join(doma, "icons"), os.path.expanduser("~/.icons"),
                    "/usr/share/icons", "/usr/local/share/icons",
                    # Flatpak: sistemski in tisti, ki jih je uporabnik namestil zase (--user).
                    "/var/lib/flatpak/exports/share/icons",
                    os.path.join(doma, "flatpak/exports/share/icons")]
        velikosti = ["128x128", "96x96", "64x64", "256x256", "48x48", "scalable"]
        teme = ["hicolor", "Papirus", "Adwaita", "breeze"]
        for koren in korenine:
            for tema in teme:
                for velikost in velikosti:
                    for konec in (".png", ".svg"):
                        pot = os.path.join(koren, tema, velikost, "apps", ime + konec)
                        if os.path.isfile(pot):
                            return pot
        for mapa in ("/usr/share/pixmaps", os.path.join(doma, "pixmaps")):
            for konec in (".png", ".svg", ".xpm"):
                pot = os.path.join(mapa, ime + konec)
                if os.path.isfile(pot):
                    return pot
        return ""
