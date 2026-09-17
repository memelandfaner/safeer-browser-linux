"""Zaslon racunalnika na televizorju (Safeer Desktop Stream, faza 1: slika).

Racunalnik zajame svoj zaslon, ga kodira v H.264 in ga poslje televizorju po **neposredni**
povezavi v domacem omrezju - nic ne gre skozi sredisce in nic v oblak. Povezava je TLS s
samopodpisanim potrdilom Controla, katerega odtis televizor dobi skupaj z enkratnim zetonom v
odgovoru na ukaz `screen.start` (ista pot in isto potrdilo kot pri datotekah).

Format je namenoma preprost: po pozdravu tece gol pretok H.264 (Annex-B), ki ga Android dekodira
strojno (MediaCodec). Brez vsebnika in brez medpomnilnika, ker je cilj cim manjsa zakasnitev.

Pozdrav (prvi vrstici, UTF-8):
    SAFEER-ZASLON <zeton>\\n        <- televizor
    {"w":1920,"h":1080,"fps":30}\\n <- racunalnik, nato gol H.264

Zvok in vnos (tipkovnica, daljinec) v tej fazi nista vkljucena; kar ni narejeno, tudi ne
obljubljamo.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import secrets
import ssl
import subprocess
import threading
import time
from typing import Dict, List, Optional

from core.link_datoteke import TLS_MAPA, zagotovi_potrdilo

#: Kolikor casa cakamo, da se televizor javi, preden sejo zavrzemo.
CAKANJE_S = 30
#: Najvecja slika, ki jo posiljamo (televizor je 4K, a 1080p je za namizje dovolj in hitreje).
NAJVEC_SIRINA, NAJVEC_VISINA = 1920, 1080
# Kvantizator (qp) je pri tem kodirniku edini vzvod kakovosti - gonilnik zna samo CQP. Izmerjeno na
# mirnem namizju: qp 28 = 0,6 Mb/s, qp 24 = 0,8, qp 20 = 0,9, qp 18 = 1,0, qp 16 = 1,3 Mb/s, in
# procesor je pri vseh enak (strosek je zajem, ne kodiranje). Ker je pasovne sirine v domacem
# omrezju na pretek, so privzete vrednosti izdatne - drobno besedilo mora biti ostro.
KAKOVOSTI = {
    "nizka": {"fps": 30, "bitrate": "4M", "qp": 26, "sirina": 1280, "visina": 720},
    "srednja": {"fps": 30, "bitrate": "8M", "qp": 20, "sirina": 1920, "visina": 1080},
    "visoka": {"fps": 60, "bitrate": "16M", "qp": 18, "sirina": 1920, "visina": 1080},
    "najvisja": {"fps": 60, "bitrate": "24M", "qp": 16, "sirina": 1920, "visina": 1080},
}
# Privzeto posljemo najboljse, kar zmoreta racunalnik in omrezje: ostrejsa slika je po meritvah
# skoraj zastonj (strosek je zajem, ne kodiranje), pasovne sirine v domacem omrezju pa je na pretek.
# Nizje stopnje ostajajo v dogovoru zato, da se bo mogoce samodejno umakniti, kadar povezava ali
# racunalnik tega ne bosta zmogla - ne zato, da bi uporabnik izbiral.
PRIVZETA_KAKOVOST = "najvisja"


def _zaslon_geometrija(display: str) -> Optional[tuple]:
    """Velikost zaslona (xdotool); brez njega ne ugibamo, ampak vrnemo None."""
    if not shutil.which("xdotool"):
        return None
    try:
        okolje = dict(os.environ, DISPLAY=display)
        r = subprocess.run(["xdotool", "getdisplaygeometry"], text=True, capture_output=True,
                           timeout=5, env=okolje)
        deli = r.stdout.split()
        if len(deli) == 2:
            return int(deli[0]), int(deli[1])
    except Exception:
        pass
    return None


def vaapi_naprava() -> Optional[str]:
    """Naprava za strojno kodiranje (Intel/AMD); None, kadar je ni."""
    for ime in ("renderD128", "renderD129"):
        pot = os.path.join("/dev/dri", ime)
        if os.path.exists(pot):
            return pot
    return None


def ukaz_ffmpeg(display: str, sirina: int, visina: int, izvor_sirina: int, izvor_visina: int,
                fps: int, bitrate: str, vaapi: Optional[str], ffmpeg: str = "ffmpeg",
                qp: int = 24) -> List[str]:
    """Ukaz za zajem in kodiranje. Strojno (VAAPI), ce je mogoce, sicer x264 brez zamika.

    Locen od zagona, da ga je mogoce preveriti v testu brez kamere in zaslona.
    """
    u = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
         "-f", "x11grab", "-draw_mouse", "1", "-framerate", str(fps),
         "-video_size", f"{izvor_sirina}x{izvor_visina}", "-i", display]
    # Kadar je slika ze prave velikosti, je ne prevzorcimo: vsako skaliranje zmehca besedilo in
    # nekaj stane. To je najpogostejsi primer (zaslon 1920x1080 -> 1920x1080).
    lestvica = (sirina, visina) != (izvor_sirina, izvor_visina)
    filter_lestvica = f"scale={sirina}:{visina}:flags=lanczos," if lestvica else ""
    if vaapi:
        # Intelov gonilnik ima na tem prenosniku samo nizkoenergijski vhod (EncSliceLP), ta pa
        # podpira le CQP - z -b:v kodirnik sploh ne odpre ("no RC mode compatible"). Zato kakovost
        # dolocimo s kvantizatorjem, hitrost pa omejimo z velikostjo slike in sliko na sekundo.
        # Profil high (CABAC, transformacija 8x8) je za besedilo opazno boljsi od main in
        # televizor ga strojno dekodira (OMX.MTK.VIDEO.DECODER.AVC).
        #
        # Varcnega nacina (low_power) namenoma ne vsiljujemo: na tem prenosniku (Intel Gen12) drug
        # nacin sploh ne obstaja - izmerjeno je z low_power 0 in 1 izid enak do decimalke - na
        # drugih racunalnikih pa lahko gonilnik izbere boljso pot, ce mu je ne zvezemo.
        # CQP je edini nacin hitrosti, ki ga ta gonilnik zna (CBR, VBR, ICQ in QVBR so preizkuseni
        # in vsi padejo), obenem pa ga zna vsak - zato kakovost dolocimo s kvantizatorjem.
        u += ["-vaapi_device", vaapi,
              "-vf", f"{filter_lestvica}format=nv12,hwupload",
              "-c:v", "h264_vaapi", "-profile:v", "high",
              "-rc_mode", "CQP", "-qp", str(qp)]
    else:
        u += ["-vf", f"{filter_lestvica}format=yuv420p",
              "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-profile:v", "high",
              "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", "1M"]
    # Brez B-slik in z rednim kljucnim okvirjem: televizor se lahko prikljuci hitro,
    # izguba paketa pa se popravi v eni sekundi.
    u += ["-g", str(max(1, fps)), "-bf", "0", "-flags", "+low_delay",
          "-f", "h264", "-"]
    return u


class Zaslon:
    """Deljenje zaslona racunalnika s televizorjem: ena seja naenkrat, samo na uporabnikov ukaz."""

    ZMOZNOST = "desktop"

    def __init__(self, tls_mapa: str = TLS_MAPA, ffmpeg: Optional[str] = None,
                 vklopljeno: bool = False) -> None:
        self.tls_mapa = tls_mapa
        #: Uporabnik mora deljenje zaslona vklopiti v Safeer Controlu; privzeto je izklopljeno.
        self.vklopljeno = bool(vklopljeno)
        #: Klicatelj (Control) ga nastavi, da si izbiro zapomni in pokaze stanje v pladnju.
        self.ob_spremembi = None
        self.ffmpeg = ffmpeg or (shutil.which("ffmpeg") or "")
        self.odtis = ""
        self.vrata = 0
        self._zeton = ""
        self._naprava = ""
        self._kakovost = PRIVZETA_KAKOVOST
        self._slika: Dict[str, int] = {}
        self._posluh: Optional[socket.socket] = None
        self._proces: Optional[subprocess.Popen] = None
        self._nit: Optional[threading.Thread] = None
        self._tece_od = 0.0
        self._povezan = False
        self._kljucavnica = threading.Lock()

    # ------------------------------------------------------------------ stanje

    def na_voljo(self) -> dict:
        """Ali ta racunalnik sploh zna deliti zaslon in s cim."""
        display = os.environ.get("DISPLAY", "")
        vaapi = vaapi_naprava()
        return {
            "dovoljeno": self.vklopljeno,
            "mozno": bool(self.ffmpeg) and bool(display),
            "ffmpeg": bool(self.ffmpeg),
            "zaslon": display,
            "strojno": bool(vaapi),
            "kakovosti": sorted(KAKOVOSTI),
        }

    def stanje(self) -> dict:
        s = {"tece": self._proces is not None or self._posluh is not None,
             "povezan": self._povezan, "naprava": self._naprava, "kakovost": self._kakovost}
        if self._slika:
            s.update(self._slika)
        if self._tece_od:
            s["sekund"] = int(time.time() - self._tece_od)
        return s

    # ------------------------------------------------------------------ zagon

    def nastavi(self, vklopljeno: bool) -> None:
        """Uporabnik je deljenje zaslona vklopil ali izklopil. Izklop takoj konca tekoco sejo."""
        self.vklopljeno = bool(vklopljeno)
        if not self.vklopljeno:
            self.ustavi()
        if self.ob_spremembi is not None:
            try:
                self.ob_spremembi(self.vklopljeno)
            except Exception:
                pass

    def zacni(self, id_naprave: str, kakovost: str = PRIVZETA_KAKOVOST) -> dict:
        """Pripravi sejo: odpre TLS vrata in caka televizor. Zajem se zacne sele, ko se ta javi."""
        if not self.vklopljeno:
            raise RuntimeError("Deljenje zaslona ni vklopljeno")
        if not self.ffmpeg:
            raise RuntimeError("Na tem racunalniku ni ffmpeg")
        display = os.environ.get("DISPLAY", "")
        if not display:
            raise RuntimeError("Zaslona ni mogoce zajeti (seja ni na voljo)")
        k = KAKOVOSTI.get(kakovost) or KAKOVOSTI[PRIVZETA_KAKOVOST]
        self.ustavi()
        izvor = _zaslon_geometrija(display) or (NAJVEC_SIRINA, NAJVEC_VISINA)
        sirina, visina = self._prilagodi(izvor, k["sirina"], k["visina"])
        with self._kljucavnica:
            self._kakovost = kakovost if kakovost in KAKOVOSTI else PRIVZETA_KAKOVOST
            self._naprava = id_naprave
            self._zeton = secrets.token_urlsafe(24)
            self._slika = {"width": sirina, "height": visina, "fps": int(k["fps"])}
            kljuc, potrdilo, self.odtis = zagotovi_potrdilo(self.tls_mapa)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(potrdilo, kljuc)
            posluh = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            posluh.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            posluh.bind(("0.0.0.0", 0))
            posluh.listen(1)
            posluh.settimeout(CAKANJE_S)
            self.vrata = posluh.getsockname()[1]
            self._posluh = posluh
            self._tece_od = time.time()
            self._povezan = False
            ukaz = ukaz_ffmpeg(display, sirina, visina, izvor[0], izvor[1], int(k["fps"]),
                               str(k["bitrate"]), vaapi_naprava(), self.ffmpeg, int(k["qp"]))
            self._nit = threading.Thread(target=self._streci, args=(posluh, ctx, ukaz),
                                         name="safeer-zaslon", daemon=True)
            self._nit.start()
        return {"port": self.vrata, "fp": self.odtis, "token": self._zeton,
                "codec": "h264", **self._slika, "quality": self._kakovost}

    @staticmethod
    def _prilagodi(izvor, najvec_sirina, najvec_visina) -> tuple:
        """Ohrani razmerje zaslona in ne povecuj cez izvirnik; sirina in visina morata biti sodi."""
        s, v = izvor
        if s <= 0 or v <= 0:
            return najvec_sirina, najvec_visina
        merilo = min(najvec_sirina / s, najvec_visina / v, 1.0)
        return (max(2, int(s * merilo) // 2 * 2), max(2, int(v * merilo) // 2 * 2))

    def _streci(self, posluh: socket.socket, ctx: ssl.SSLContext, ukaz: List[str]) -> None:
        odjemalec = None
        try:
            surov, _ = posluh.accept()
            odjemalec = ctx.wrap_socket(surov, server_side=True)
            odjemalec.settimeout(10)
            pozdrav = self._preberi_vrstico(odjemalec)
            if not pozdrav.startswith("SAFEER-ZASLON ") or pozdrav.split(" ", 1)[1].strip() != self._zeton:
                odjemalec.close()
                return
            odjemalec.sendall((json.dumps({"w": self._slika["width"], "h": self._slika["height"],
                                           "fps": self._slika["fps"]}) + "\n").encode("utf-8"))
            odjemalec.settimeout(None)
            self._povezan = True
            proces = subprocess.Popen(ukaz, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                      stdin=subprocess.DEVNULL, bufsize=0)
            self._proces = proces
            while True:
                kos = proces.stdout.read(32 * 1024)
                if not kos:
                    break
                odjemalec.sendall(kos)
        except (OSError, ssl.SSLError, ValueError):
            pass
        finally:
            self._povezan = False
            try:
                if odjemalec is not None:
                    odjemalec.close()
            except Exception:
                pass
            self.ustavi()

    @staticmethod
    def _preberi_vrstico(s: socket.socket, najvec: int = 256) -> str:
        zbrano = b""
        while len(zbrano) < najvec:
            b = s.recv(1)
            if not b or b == b"\n":
                break
            zbrano += b
        return zbrano.decode("utf-8", "replace")

    def ustavi(self) -> None:
        """Konca zajem in zapre vrata; zeton takoj ne velja vec."""
        with self._kljucavnica:
            proces, posluh = self._proces, self._posluh
            self._proces = None
            self._posluh = None
            self._zeton = ""
            self.vrata = 0
            self._tece_od = 0.0
        if proces is not None:
            try:
                proces.terminate()
                proces.wait(timeout=3)
            except Exception:
                try:
                    proces.kill()
                except Exception:
                    pass
        if posluh is not None:
            # Nit visi v accept(); samo close() je ne prebudi vedno, shutdown() pa jo.
            try:
                posluh.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                posluh.close()
            except Exception:
                pass


__all__ = ["Zaslon", "ukaz_ffmpeg", "vaapi_naprava", "KAKOVOSTI", "PRIVZETA_KAKOVOST"]
