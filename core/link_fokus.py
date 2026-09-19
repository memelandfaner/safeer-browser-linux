"""Premik po poljih programa s krizcem (locen zaslon za televizor).

Na televizorju je naravno, da smerna tipka skoci na naslednji gumb, ne da miska potuje cez zaslon.
Namizni programi tega ne znajo sami, zato to naredimo mi: prek dostopnosti (AT-SPI) preberemo, kje
so v oknu gumbi, polja in povezave, in kazalec postavimo na sredino najblizjega v smeri, ki jo je
uporabnik pritisnil. Program pod kazalcem pokaze, kaj je izbrano (poudarek ob lebdenju), OK ali A
klikne. Kjer program o sebi nic ne pove (igre), vrnemo False - takrat gre smerna tipka kot tipka.

Nic ne spreminjamo in nic ne beremo iz vsebine: samo vloge, stanja in pravokotnike elementov.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import threading
import time
from typing import List, Optional, Tuple

#: Kaj je smiselno izbrati s krizcem.
VLOGE = {
    "push button", "button", "toggle button", "check box", "radio button", "menu item",
    "check menu item", "radio menu item", "combo box", "entry", "text", "password text",
    "link", "list item", "page tab", "slider", "spin button", "icon", "tree item", "table cell",
    "menu", "switch",
}
#: Meje, da en pritisk nikoli ne traja dolgo tudi v velikem programu.
NAJVEC_ELEMENTOV = 1500
NAJVEC_GLOBINA = 60
#: Kako dolgo velja prebrani seznam elementov (okno se med brskanjem redko spremeni).
VELJA_S = 8.0


def _atspi():
    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
        return Atspi
    except Exception:
        return None


Element = Tuple[float, float, int, int, int, int]   # sredina x, y ter x, y, sirina, visina (zaslon)


def izberi(elementi: List[Element], tocka: Tuple[float, float], smer: str) -> Optional[Element]:
    """Najblizji element v smeri. Najprej v stozcu 45 stopinj, sicer kjerkoli na tisti strani."""
    x0, y0 = tocka
    najboljsi, ocena_naj = None, None
    for stozec in (True, False):
        for e in elementi:
            dx, dy = e[0] - x0, e[1] - y0
            if smer == "desno":
                glavna, precna = dx, dy
            elif smer == "levo":
                glavna, precna = -dx, dy
            elif smer == "dol":
                glavna, precna = dy, dx
            elif smer == "gor":
                glavna, precna = -dy, dx
            else:
                return None
            if glavna <= 4:
                continue
            if stozec and abs(precna) > glavna:
                continue
            ocena = glavna + 2.5 * abs(precna)
            if ocena_naj is None or ocena < ocena_naj:
                najboljsi, ocena_naj = e, ocena
        if najboljsi is not None:
            return najboljsi
    return None


class Fokus:
    """Premikanje po poljih okna, ki je v ospredju na drugem zaslonu."""

    def __init__(self, drugi) -> None:
        self.drugi = drugi
        self._kljuc = threading.Lock()
        self._predpomnilnik: Tuple[float, object, List[Element]] = (0.0, None, [])
        #: Kje je kazalec po nasi vednosti (zaslonske koordinate); None = ne vemo.
        self.tocka: Optional[Tuple[float, float]] = None

    def ustavi(self) -> None:
        p, self._pomocnik = self._pomocnik, None
        if p is not None:
            try:
                p.kill()
                p.wait(2)
            except Exception:
                pass
        self.pozabi()
        self.tocka = None

    def pozabi(self) -> None:
        """Po kliku se okno lahko spremeni: naslednji pritisk prebere elemente znova."""
        self._predpomnilnik = (0.0, None, [])

    # ------------------------------------------------------------------ okno in elementi
    def _okno(self) -> Optional[Tuple[int, int, int, int, int]]:
        """(pid, x, y, sirina, visina) okna v ospredju na drugem zaslonu."""
        try:
            drevo = json.loads(self.drugi._msg([], "get_tree") or "{}")
        except ValueError:
            return None
        najdeno = []

        def hodi(n):
            if n.get("focused") and n.get("pid"):
                najdeno.append(n)
            for o in n.get("nodes", []) + n.get("floating_nodes", []):
                hodi(o)
        hodi(drevo)
        if not najdeno:
            return None
        n = najdeno[0]
        r, w = n.get("rect") or {}, n.get("window_rect") or {}
        return (int(n["pid"]), int(r.get("x", 0)) + int(w.get("x", 0)), int(r.get("y", 0)) + int(w.get("y", 0)),
                int(w.get("width", r.get("width", 0))), int(w.get("height", r.get("height", 0))))

    def _elementi(self, okno) -> List[Element]:
        zdaj = time.monotonic()
        cas, kljuc, elementi = self._predpomnilnik
        if kljuc == okno and zdaj - cas < VELJA_S:
            return elementi
        elementi = self._vprasaj_pomocnika(okno)
        self._predpomnilnik = (zdaj, okno, elementi)
        return elementi

    # AT-SPI v procesu Controla (GTK, vec niti) je Control sesul - zato bere locen proces. Ce ta
    # pade ali obvisi, ga ubijemo in naslednjic zazenemo znova; Control ostane ziv.
    _pomocnik: Optional[subprocess.Popen] = None

    @staticmethod
    def _okolje_pomocnika(koren: str) -> dict:
        # Brez DISPLAY: z njim AT-SPI vzame vodilo glavnega namizja (lastnost korena X :0), programi
        # na drugem zaslonu pa so na vodilu seje (org.a11y.Bus) - tam jih je videl samo brez njega.
        o = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        o["PYTHONPATH"] = koren
        return o

    def _vprasaj_pomocnika(self, okno) -> List[Element]:
        for _ in range(2):
            p = self._pomocnik
            if p is None or p.poll() is not None:
                koren = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                try:
                    p = subprocess.Popen([sys.executable, "-m", "core.link_fokus"], cwd=koren,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                         env=self._okolje_pomocnika(koren))
                except Exception:
                    return []
                self._pomocnik = p
            try:
                p.stdin.write(json.dumps(list(okno)) + "\n")
                p.stdin.flush()
                pripravljen, _, _ = select.select([p.stdout], [], [], 4.0)
                vrstica = p.stdout.readline() if pripravljen else ""
                if vrstica:
                    return [tuple(e) for e in json.loads(vrstica)]
            except Exception:
                pass
            try:
                p.kill()
            except Exception:
                pass
            self._pomocnik = None
        return []


    # ------------------------------------------------------------------ premik
    def premakni(self, smer: str) -> bool:
        """Kazalec na naslednji element v smeri. False, kadar okno o sebi nic ne pove (igra)."""
        with self._kljuc:
            okno = self._okno()
            if okno is None:
                return False
            elementi = self._elementi(okno)
            if not elementi:
                print("[fokus] okno %s: ni elementov" % (okno,), flush=True)
                return False
            _, ox, oy, sirina, visina = okno
            t = self.tocka
            if t is None or not (ox <= t[0] <= ox + sirina and oy <= t[1] <= oy + visina):
                # Prvi pritisk: element najblize sredini okna, da uporabnik vidi, kje je.
                sredina = (ox + sirina / 2.0, oy + visina / 2.0)
                cilj = min(elementi, key=lambda e: (e[0] - sredina[0]) ** 2 + (e[1] - sredina[1]) ** 2)
            else:
                cilj = izberi(elementi, t, smer)
                if cilj is None:
                    return True          # na robu: ostanemo, kjer smo (ne skocimo drugam)
            self.tocka = (cilj[0], cilj[1])
            ok = self.drugi.vnos.absolutno(int(cilj[0]), int(cilj[1]))
            if not ok:
                print("[fokus] premik kazalca ni uspel", flush=True)
            return ok

def preberi_elemente(okno) -> List[Element]:
    """V pomoznem procesu: elementi okna (pid, x, y, sirina, visina) prek AT-SPI."""
    if True:   # (telo je bilo prej metoda razreda)
        Atspi = _atspi()
        if Atspi is None:
            return []
        pid, ox, oy, sirina, visina = okno
        aplikacija = None
        try:
            namizje = Atspi.get_desktop(0)
            for i in range(namizje.get_child_count()):
                a = namizje.get_child_at_index(i)
                try:
                    if a is not None and a.get_process_id() == pid:
                        aplikacija = a
                        break
                except Exception:
                    continue
        except Exception:
            return []
        elementi = []
        if aplikacija is not None:
            pregledanih = [0]

            def zberi(o, globina):
                if o is None or globina > NAJVEC_GLOBINA or pregledanih[0] > NAJVEC_ELEMENTOV:
                    return
                pregledanih[0] += 1
                try:
                    st = o.get_state_set()
                    # Aplikacija sama (koren) ni "prikazana"; skrite veje pod njo preskocimo.
                    if globina > 0 and not st.contains(Atspi.StateType.SHOWING):
                        return
                    vloga = o.get_role_name()
                    if vloga in VLOGE and st.contains(Atspi.StateType.SENSITIVE) and \
                            (vloga not in ("text",) or st.contains(Atspi.StateType.EDITABLE)):
                        e = o.get_extents(Atspi.CoordType.WINDOW)
                        if e.width > 2 and e.height > 2 and 0 <= e.x < sirina and 0 <= e.y < visina:
                            x, y = ox + e.x, oy + e.y
                            elementi.append((x + e.width / 2.0, y + e.height / 2.0, x, y, e.width, e.height))
                    for i in range(o.get_child_count()):
                        zberi(o.get_child_at_index(i), globina + 1)
                except Exception:
                    return
            zberi(aplikacija, 0)
        return elementi


def _streznik() -> None:
    """Pomozni proces: ena vrstica JSON (okno) noter, ena vrstica JSON (elementi) ven."""
    for vrstica in sys.stdin:
        try:
            elementi = preberi_elemente(tuple(json.loads(vrstica)))
        except Exception:
            elementi = []
        sys.stdout.write(json.dumps(elementi) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    _streznik()


__all__ = ["Fokus", "izberi", "VLOGE"]
