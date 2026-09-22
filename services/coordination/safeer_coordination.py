#!/usr/bin/env python3
"""Safeer Coordination (referencna storitev za Global Mesh; privzeto izklopljena).

Samo metapodatki in signalizacija med seznanjenimi napravami: prisotnost (odtis javnega kljuca,
namigi kandidatov) in kratka sporocila za vzpostavitev povezave. Nikoli zasebni kljuci naprav ali
uporabniska vsebina. Brez SAFEER_COORDINATION_SECRET storitev zavrne vse (razen /health).
Za javno rabo: za HTTPS/WSS obratnim posredovalnikom in s pravo avtentikacijo (Safeer seznanitve).
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import os
import threading
import time
from urllib.parse import parse_qs, urlparse

TTL_MAX = 120
SIGNAL_TTL = 60
NAJVEC_SIGNALOV = 64        # na prejemnika: poplava enega posiljatelja ne napolni pomnilnika
NAJVEC_NAPRAV = 10000
records: dict = {}
signals: dict = {}
_zaklep = threading.Lock()
SECRET = os.environ.get("SAFEER_COORDINATION_SECRET", "").encode()


def _clean(now=None):
    now = int(time.time() if now is None else now)
    for d in list(records):
        if records[d]["expires_at"] <= now:
            records.pop(d, None)
    for d in list(signals):
        signals[d] = [s for s in signals[d] if s["expires_at"] > now]
        if not signals[d]:
            signals.pop(d, None)


def _auth(device_id, token):
    """Referencni zeton: HMAC(secret, device_id). V produkciji ga zamenja avtentikacija Safeer seznanitev."""
    if not SECRET or not device_id or not token or len(device_id) > 128:
        return False
    expected = hmac.new(SECRET, device_id.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, token)


def objavi_prisotnost(me, b):
    fp = str(b.get("public_key_fingerprint", ""))[:256]
    hints = b.get("candidate_hints", [])
    if not fp or not isinstance(hints, list) or len(hints) > 32:
        return 400, {"error": "invalid_presence"}
    try:
        ttl = max(15, min(int(b.get("ttl", 60)), TTL_MAX))
    except (TypeError, ValueError):
        return 400, {"error": "invalid_ttl"}
    with _zaklep:
        if me not in records and len(records) >= NAJVEC_NAPRAV:
            return 503, {"error": "busy"}
        records[me] = {"device_id": me, "public_key_fingerprint": fp,
                       "candidate_hints": [str(x)[:512] for x in hints], "expires_at": int(time.time()) + ttl}
    return 200, {"ok": True, "ttl": ttl}


def poslji_signal(me, b):
    peer = str(b.get("to", ""))[:128]
    payload = b.get("payload")
    if not peer or payload is None or peer == me:
        return 400, {"error": "invalid_signal"}
    if len(json.dumps(payload)) > 32768:
        return 413, {"error": "signal_too_large"}
    with _zaklep:
        vrsta = signals.setdefault(peer, [])
        if len(vrsta) >= NAJVEC_SIGNALOV:
            return 429, {"error": "too_many_signals"}
        vrsta.append({"from": me, "payload": payload, "expires_at": int(time.time()) + SIGNAL_TTL})
    return 202, {"ok": True}


class Handler(BaseHTTPRequestHandler):
    server_version = "SafeerCoordination"
    sys_version = ""

    def _json(self, status, obj):
        b = json.dumps(obj, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length", "0"))
        if n < 0 or n > 65536:
            raise ValueError("body size")
        b = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(b, dict):
            raise ValueError("not an object")
        return b

    def _identity(self):
        d = self.headers.get("X-Safeer-Device-Id", "")
        t = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        return d if _auth(d, t) else None

    def do_GET(self):
        with _zaklep:
            _clean()
        u = urlparse(self.path)
        if u.path == "/health":
            return self._json(200, {"ok": True, "service": "safeer-coordination"})
        me = self._identity()
        if not me:
            return self._json(401, {"error": "unauthorized"})
        if u.path == "/v1/presence":
            peer = parse_qs(u.query).get("device_id", [""])[0]
            # Produkcija: vrni samo, ce sta me in peer v istem krogu zaupanja.
            with _zaklep:
                return self._json(200, {"presence": records.get(peer)})
        if u.path == "/v1/signals":
            with _zaklep:
                out = signals.pop(me, [])
            return self._json(200, {"signals": out})
        return self._json(404, {"error": "not_found"})

    def do_POST(self):
        with _zaklep:
            _clean()
        me = self._identity()
        if not me:
            return self._json(401, {"error": "unauthorized"})
        try:
            b = self._body()
        except Exception:
            return self._json(400, {"error": "bad_json"})
        if self.path == "/v1/presence":
            return self._json(*objavi_prisotnost(me, b))
        if self.path == "/v1/signal":
            return self._json(*poslji_signal(me, b))
        return self._json(404, {"error": "not_found"})

    def log_message(self, fmt, *args):
        pass


def main():
    host = os.environ.get("SAFEER_COORDINATION_HOST", "127.0.0.1")
    port = int(os.environ.get("SAFEER_COORDINATION_PORT", "8787"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
