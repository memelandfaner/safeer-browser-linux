"""Vnos s televizorja na racunalnik (Safeer Desktop Stream, faza 2).

Televizor poslje dogodek, racunalnik ga odigra na svojem namizju: tipka, besedilo, premik miske,
klik, kolesce. Nic drugega - ukazov z omrezja **ne** izvajamo. Vsak dogodek gre skozi seznam
dovoljenega; kar ni na njem, se tiho zavrze.

Na seji X11 to opravi `xdotool`, ki dogodke vstavi prek XTEST. Imena tipk so nasa, ne uporabnikova:
televizor poslje oznako (`gor`, `ok`, `nazaj`, `f5` ...), mi jo prevedemo v tisto, kar razume X.
Besedilo gre v `xdotool type` kot argument za `--`, nikoli skozi lupino.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Dict, Optional

#: Kaj televizor sme poslati kot tipko in v kaj to prevedemo za X.
TIPKE: Dict[str, str] = {
    "gor": "Up", "dol": "Down", "levo": "Left", "desno": "Right",
    "ok": "Return", "nazaj": "Escape", "domov": "super", "meni": "Menu",
    "presledek": "space", "vnasalka": "Return", "vracalka": "BackSpace",
    "brisalka": "Delete", "tabulator": "Tab", "ubezna": "Escape",
    "stran_gor": "Page_Up", "stran_dol": "Page_Down", "zacetek": "Home", "konec": "End",
    "predvajaj": "XF86AudioPlay", "ustavi": "XF86AudioStop",
    "naprej": "XF86AudioNext", "prejsnja": "XF86AudioPrev",
    "glasneje": "XF86AudioRaiseVolume", "tiseje": "XF86AudioLowerVolume", "utisaj": "XF86AudioMute",
    "celozaslonsko": "F11", "osvezi": "F5", "isci": "ctrl+f",
    "kopiraj": "ctrl+c", "prilepi": "ctrl+v", "izrezi": "ctrl+x", "razveljavi": "ctrl+z",
    "zapri_okno": "ctrl+w", "preklopi_okno": "alt+Tab",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5", "f6": "F6",
    "f7": "F7", "f8": "F8", "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
}

#: Gumbi miske: levi, srednji, desni in kolesce (4 gor, 5 dol).
GUMBI = {"levi": "1", "srednji": "2", "desni": "3"}
KOLESCE = {"gor": "4", "dol": "5"}

#: Najvec, kolikor se premaknemo z enim dogodkom, in najdaljse besedilo naenkrat.
NAJVEC_PREMIK = 400
NAJVEC_BESEDILA = 200


class Vnos:
    """Odigra dogodke televizorja na namizju. Brez xdotool ne naredi nicesar in to tudi pove."""

    def __init__(self, display: Optional[str] = None, xdotool: Optional[str] = None) -> None:
        self.display = display
        self.xdotool = xdotool if xdotool is not None else (shutil.which("xdotool") or "")
        self.stevec = 0

    @property
    def mozno(self) -> bool:
        return bool(self.xdotool)

    def izvedi(self, dogodek: dict) -> bool:
        """Vrne True, kadar smo dogodek res odigrali."""
        if not self.mozno or not isinstance(dogodek, dict):
            return False
        vrsta = str(dogodek.get("vrsta", "") or "")
        if vrsta == "tipka":
            return self._tipka(str(dogodek.get("tipka", "") or ""))
        if vrsta == "besedilo":
            return self._besedilo(str(dogodek.get("besedilo", "") or ""))
        if vrsta == "premik":
            return self._premik(dogodek.get("dx"), dogodek.get("dy"))
        if vrsta == "klik":
            return self._klik(str(dogodek.get("gumb", "levi") or "levi"), bool(dogodek.get("dvojni")))
        if vrsta == "kolesce":
            return self._kolesce(str(dogodek.get("smer", "") or ""), dogodek.get("koliko"))
        return False

    # ------------------------------------------------------------------ posamezni dogodki

    def _tipka(self, oznaka: str) -> bool:
        tipka = TIPKE.get(oznaka.strip().lower())
        if tipka is None:
            return False
        return self._pozeni(["key", "--clearmodifiers", tipka])

    def _besedilo(self, besedilo: str) -> bool:
        besedilo = besedilo[:NAJVEC_BESEDILA]
        if not besedilo or any(ord(z) < 32 for z in besedilo):
            return False
        return self._pozeni(["type", "--clearmodifiers", "--delay", "12", "--", besedilo])

    def _premik(self, dx, dy) -> bool:
        try:
            x = max(-NAJVEC_PREMIK, min(NAJVEC_PREMIK, int(dx)))
            y = max(-NAJVEC_PREMIK, min(NAJVEC_PREMIK, int(dy)))
        except (TypeError, ValueError):
            return False
        if x == 0 and y == 0:
            return False
        return self._pozeni(["mousemove_relative", "--", str(x), str(y)])

    def _klik(self, gumb: str, dvojni: bool) -> bool:
        st = GUMBI.get(gumb.strip().lower())
        if st is None:
            return False
        ukaz = ["click", "--clearmodifiers"]
        if dvojni:
            ukaz += ["--repeat", "2"]
        return self._pozeni(ukaz + [st])

    def _kolesce(self, smer: str, koliko) -> bool:
        st = KOLESCE.get(smer.strip().lower())
        if st is None:
            return False
        try:
            n = max(1, min(10, int(koliko or 1)))
        except (TypeError, ValueError):
            n = 1
        return self._pozeni(["click", "--repeat", str(n), st])

    def _pozeni(self, argumenti) -> bool:
        import os
        okolje = dict(os.environ)
        if self.display:
            okolje["DISPLAY"] = self.display
        try:
            subprocess.run([self.xdotool] + argumenti, check=False, timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=okolje)
        except Exception:
            return False
        self.stevec += 1
        return True


__all__ = ["Vnos", "TIPKE", "GUMBI", "KOLESCE"]
