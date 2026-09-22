// Safeer Coordination (Global Mesh): Cloudflare Worker + en Durable Object (SQLite, brezplacen nacrt).
//
// Samo metapodatki za srecanje seznanjenih naprav: prisotnost (namigi kandidatov, TTL) in kratki
// signali (ICE/SDP). Nikoli zasebni kljuci ali uporabniska vsebina; vse je v pomnilniku in potece.
//
// Avtentikacija brez skupne skrivnosti: vsaka zahteva je podpisana s kljucem naprave (ECDSA P-256,
// isti kljuc kot v krogu zaupanja). Id naprave = "n-" + prvih 16 hex SHA-256(SPKI), kot KrogZaupanja.
// Glave: X-Safeer-Key (SPKI base64), X-Safeer-Time (unix s), X-Safeer-Signature (DER base64) nad
//   METODA "\n" POT "\n" CAS "\n" hex(SHA-256(telo))
// Zasebnost: prisotnost naprave vidi in ji signal poslje samo naprava s seznama `allow`, ki ga
// objavi naprava sama (njen krog zaupanja). Tujec ne izve niti, ali naprava obstaja.

export const TTL_MAX = 120;
export const SIGNAL_TTL = 60;
export const NAJVEC_SIGNALOV = 64;
export const NAJVEC_NAPRAV = 10000;
export const ODMIK_URE = 120;
const ID = /^n-[0-9a-f]{16}$/;

const enc = new TextEncoder();
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const b64d = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

export async function idIzKljuca(spkiB64) {
  return "n-" + hex(await crypto.subtle.digest("SHA-256", b64d(spkiB64))).slice(0, 16);
}

/** DER ECDSA podpis (Java SHA256withECDSA) -> surovi r||s (64 B), kot ga zahteva WebCrypto. */
export function derVSurovo(der) {
  let i = 0;
  if (der[i++] !== 0x30) throw new Error("der");
  if (der[i] & 0x80) i += 1 + (der[i] & 0x7f); else i++;
  const del = () => {
    if (der[i++] !== 0x02) throw new Error("der");
    const n = der[i++];
    let v = der.slice(i, i + n); i += n;
    while (v.length > 32 && v[0] === 0) v = v.slice(1);
    if (v.length > 32) throw new Error("der");
    const o = new Uint8Array(32); o.set(v, 32 - v.length); return o;
  };
  const r = del(), s = del();
  const out = new Uint8Array(64); out.set(r); out.set(s, 32); return out;
}

/** Vrne id naprave ali null. `zdaj` v sekundah (za teste). */
export async function preveri(metoda, pot, glave, telo, zdaj = Math.floor(Date.now() / 1000)) {
  const kljuc = glave.get("x-safeer-key") || "", cas = glave.get("x-safeer-time") || "", podpis = glave.get("x-safeer-signature") || "";
  if (!kljuc || !cas || !podpis || kljuc.length > 400 || podpis.length > 200) return null;
  const t = Number(cas);
  if (!Number.isInteger(t) || Math.abs(zdaj - t) > ODMIK_URE) return null;
  try {
    const k = await crypto.subtle.importKey("spki", b64d(kljuc), { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"]);
    const izvlecek = hex(await crypto.subtle.digest("SHA-256", enc.encode(telo)));
    const sporocilo = enc.encode(`${metoda}\n${pot}\n${cas}\n${izvlecek}`);
    const ok = await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, k, derVSurovo(b64d(podpis)), sporocilo);
    return ok ? await idIzKljuca(kljuc) : null;
  } catch {
    return null;
  }
}

/** Stanje koordinacije (v pomnilniku); loceno od omrezja, da ga lahko testiramo. */
export class Stanje {
  constructor() { this.prisotnost = new Map(); this.signali = new Map(); }

  pocisti(zdaj) {
    for (const [d, r] of this.prisotnost) if (r.expires_at <= zdaj) this.prisotnost.delete(d);
    for (const [d, v] of this.signali) {
      const ziv = v.filter((s) => s.expires_at > zdaj);
      if (ziv.length) this.signali.set(d, ziv); else this.signali.delete(d);
    }
  }

  objavi(me, b, zdaj) {
    const hints = b.candidate_hints ?? [], allow = b.allow ?? [];
    if (!Array.isArray(hints) || hints.length > 32 || !Array.isArray(allow) || allow.length > 256) return [400, { error: "invalid_presence" }];
    if (!allow.every((a) => typeof a === "string" && ID.test(a))) return [400, { error: "invalid_allow" }];
    const ttl = Number.isFinite(Number(b.ttl ?? 60)) ? Math.max(15, Math.min(Math.trunc(Number(b.ttl ?? 60)), TTL_MAX)) : NaN;
    if (Number.isNaN(ttl)) return [400, { error: "invalid_ttl" }];
    if (!this.prisotnost.has(me) && this.prisotnost.size >= NAJVEC_NAPRAV) return [503, { error: "busy" }];
    this.prisotnost.set(me, { device_id: me, candidate_hints: hints.map((x) => String(x).slice(0, 512)), allow, expires_at: zdaj + ttl });
    return [200, { ok: true, ttl }];
  }

  poisci(me, peer) {
    const r = this.prisotnost.get(peer);
    // Enak odgovor za "ni" in "ni dovoljeno": tujec ne izve, ali naprava obstaja.
    if (!r || !r.allow.includes(me)) return [200, { presence: null }];
    return [200, { presence: { device_id: r.device_id, candidate_hints: r.candidate_hints, expires_at: r.expires_at } }];
  }

  poslji(me, b, zdaj) {
    const peer = String(b.to ?? "");
    if (!ID.test(peer) || peer === me || b.payload === undefined) return [400, { error: "invalid_signal" }];
    if (JSON.stringify(b.payload).length > 32768) return [413, { error: "signal_too_large" }];
    const r = this.prisotnost.get(peer);
    if (!r || !r.allow.includes(me)) return [202, { ok: true }]; // tiho zavrzemo: brez razkritja
    const v = this.signali.get(peer) ?? [];
    if (v.length >= NAJVEC_SIGNALOV) return [429, { error: "too_many_signals" }];
    v.push({ from: me, payload: b.payload, expires_at: zdaj + SIGNAL_TTL });
    this.signali.set(peer, v);
    return [202, { ok: true }];
  }

  prevzemi(me) { const v = this.signali.get(me) ?? []; this.signali.delete(me); return [200, { signals: v.map(({ from, payload }) => ({ from, payload })) }]; }
}

const json = (status, obj) => new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

export async function obdelaj(stanje, request, zdaj = Math.floor(Date.now() / 1000)) {
  const url = new URL(request.url);
  if (url.pathname === "/health") return json(200, { ok: true, service: "safeer-coordination" });
  const telo = request.method === "POST" ? await request.text() : "";
  if (telo.length > 65536) return json(413, { error: "too_large" });
  const me = await preveri(request.method, url.pathname + url.search, request.headers, telo, zdaj);
  if (!me) return json(401, { error: "unauthorized" });
  stanje.pocisti(zdaj);
  let b = {};
  if (request.method === "POST") {
    try { b = JSON.parse(telo || "{}"); } catch { return json(400, { error: "bad_json" }); }
    if (!b || typeof b !== "object" || Array.isArray(b)) return json(400, { error: "bad_json" });
  }
  const pot = `${request.method} ${url.pathname}`;
  if (pot === "POST /v1/presence") return json(...stanje.objavi(me, b, zdaj));
  if (pot === "GET /v1/presence") return json(...stanje.poisci(me, url.searchParams.get("device_id") || ""));
  if (pot === "POST /v1/signal") return json(...stanje.poslji(me, b, zdaj));
  if (pot === "GET /v1/signals") return json(...stanje.prevzemi(me));
  return json(404, { error: "not_found" });
}

export class Koordinacija {
  constructor() { this.stanje = new Stanje(); }
  fetch(request) { return obdelaj(this.stanje, request); }
}

export default {
  async fetch(request, env) {
    if (env.SAFEER_GLOBAL_LINK_ENABLED !== "true" && new URL(request.url).pathname !== "/health") {
      return json(503, { error: "disabled" });
    }
    return env.KOORDINACIJA.get(env.KOORDINACIJA.idFromName("glavna")).fetch(request);
  },
};
