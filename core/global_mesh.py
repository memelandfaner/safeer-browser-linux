"""Safeer Global Mesh (temelj, se ni vklopljen): kako doseci seznanjeno napravo zunaj domacega omrezja.

Vrstni red je vedno LOCAL -> DIRECT_INTERNET -> RELAY -> OFFLINE: LAN zmaga vedno, internet in rele
sta izrecna izbira uporabnika, neseznanjena naprava ali naprava brez kljuca ni dosegljiva nikoli.
Enaka politika je v Kotlinu (tv-browser-2: link/GlobalMesh.kt). Koordinacija: services/coordination (Cloudflare Worker na link.safeer.si).
"""
from dataclasses import dataclass, field
from enum import Enum
from time import time

class Reachability(str, Enum):
    LOCAL="local"
    DIRECT_INTERNET="direct_internet"
    RELAY="relay"
    OFFLINE="offline"

@dataclass(frozen=True)
class Peer:
    device_id: str
    paired: bool
    public_key_fingerprint: str
    local_reachable: bool=False
    direct_internet_reachable: bool=False
    relay_reachable: bool=False

@dataclass(frozen=True)
class MeshPolicy:
    internet_enabled: bool=False
    relay_enabled: bool=False
    def route(self, peer: Peer):
        if not peer.paired or not peer.public_key_fingerprint:
            return Reachability.OFFLINE
        if peer.local_reachable:
            return Reachability.LOCAL
        if not self.internet_enabled:
            return Reachability.OFFLINE
        if peer.direct_internet_reachable:
            return Reachability.DIRECT_INTERNET
        if self.relay_enabled and peer.relay_reachable:
            return Reachability.RELAY
        return Reachability.OFFLINE

@dataclass
class PresenceRecord:
    device_id: str
    public_key_fingerprint: str
    expires_at: int
    candidate_hints: list[str] = field(default_factory=list)
    def valid(self, now=None):
        return bool(self.device_id and self.public_key_fingerprint) and self.expires_at > int(time() if now is None else now)

class PresenceRegistry:
    """In-memory reference registry for tests/local coordination.
    Production deployment should use authenticated HTTPS/WSS storage with TTL.
    Never store device private keys or user payloads here.
    """
    def __init__(self): self._records={}
    def announce(self, record: PresenceRecord):
        if not record.valid(): raise ValueError("invalid/expired presence")
        self._records[record.device_id]=record
    def lookup(self, device_id: str, now=None):
        r=self._records.get(device_id)
        return r if r and r.valid(now) else None
