// Safeer Coordination (Global Mesh): Cloudflare Worker + Durable Object za vsako napravo (SQLite, brezplacen nacrt).
//
// Srecanje seznanjenih naprav: prisotnost (TTL), kratki signali in rele. Rele je cev za bajte med
// napravo in njenim hubom: skozi tece TLS Safeer Linka od konca do konca (odtis kljuca huba), zato rele
// vidi samo sifrirano vsebino. Nikoli zasebni kljuci; prisotnost v SQLite objekta naprave, signali v pomnilniku.
//
// Avtentikacija brez skupne skrivnosti: vsaka zahteva je podpisana s kljucem naprave (ECDSA P-256,
// isti kljuc kot v krogu zaupanja). Id naprave = "n-" + prvih 16 hex SHA-256(SPKI), kot KrogZaupanja.
// Glave: X-Safeer-Key (SPKI base64), X-Safeer-Time (unix s), X-Safeer-Signature (DER base64) nad
//   METODA "\n" POT "\n" CAS "\n" hex(SHA-256(telo))
// Zasebnost: Global Link je za vsakega uporabnika samo njegov krog zaupanja. Prisotnost naprave vidi in
// ji signal poslje samo naprava s seznama `allow`, ki ga objavi naprava sama (clani njenega kroga, kot jih
// je seznanil Safeer Link). Drug uporabnik vidi le svoje naprave; o tujih ne izve niti, ali obstajajo.
// Vsaka naprava ima svoj Durable Object (ime = id naprave): ni skupnega seznama vseh naprav, ki bi ga
// lahko kdo bral ali napolnil.

export const TTL_MAX = 120;
export const SIGNAL_TTL = 60;
export const NAJVEC_SIGNALOV = 64;
export const ODMIK_URE = 120;
const ID = /^n-[0-9a-f]{16}$/;
const KANAL = /^[0-9a-f]{32}$/;
export const NAJVEC_KANALOV = 32;

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

/**
 * Javni vhod: preveri podpis, nato zahtevo preda Durable Objectu naprave, ki jo zadeva
 * (lastna prisotnost in signali: moj; iskanje in posiljanje: ciljna naprava). `imenik(ime)` vrne stub.
 */
export async function usmeri(imenik, request, zdaj = Math.floor(Date.now() / 1000)) {
  const url = new URL(request.url);
  if (url.pathname === "/health") return json(200, { ok: true, service: "safeer-coordination" });
  const telo = request.method === "POST" ? await request.text() : "";
  if (telo.length > 65536) return json(413, { error: "too_large" });
  const me = await preveri(request.method, url.pathname + url.search, request.headers, telo, zdaj);
  if (!me) return json(401, { error: "unauthorized" });
  let b = {};
  if (request.method === "POST") {
    try { b = JSON.parse(telo || "{}"); } catch { return json(400, { error: "bad_json" }); }
    if (!b || typeof b !== "object" || Array.isArray(b)) return json(400, { error: "bad_json" });
  }
  const pot = `${request.method} ${url.pathname}`;
  // Rele (WebSocket): hub poslusa in sprejema kanale, naprava iz njegovega kroga se poveze.
  const rele = { "GET /v1/listen": "poslusaj", "GET /v1/accept": "sprejmi", "GET /v1/connect": "povezi" }[pot];
  if (rele) {
    if (request.headers.get("upgrade") !== "websocket") return json(426, { error: "websocket_required" });
    const kanal = url.searchParams.get("kanal") || "";
    const cilj = rele === "povezi" ? (url.searchParams.get("to") || "") : me;
    if (!ID.test(cilj) || (rele !== "poslusaj" && !KANAL.test(kanal))) return json(400, { error: "invalid_relay" });
    if (cilj === me && rele === "povezi") return json(400, { error: "invalid_relay" });
    return imenik(cilj).fetch(new Request(`https://do/${rele}?kanal=${kanal}`, {
      headers: { upgrade: "websocket", "x-safeer-me": me } }));
  }
  let cilj, dejanje;
  if (pot === "POST /v1/presence") { cilj = me; dejanje = "objavi"; }
  else if (pot === "GET /v1/signals") { cilj = me; dejanje = "prevzemi"; }
  else if (pot === "GET /v1/presence") { cilj = url.searchParams.get("device_id") || ""; dejanje = "poisci"; }
  else if (pot === "POST /v1/signal") { cilj = String(b.to ?? ""); dejanje = "poslji"; }
  else return json(404, { error: "not_found" });
  if (!ID.test(cilj)) return dejanje === "poisci" ? json(200, { presence: null }) : json(400, { error: "invalid_target" });
  if (dejanje === "poslji" && cilj === me) return json(400, { error: "invalid_signal" });
  // Notranja zahteva do Durable Objecta; od zunaj ni dosegljiv, zato mu `me` lahko zaupa.
  return imenik(cilj).fetch(new Request("https://do/" + dejanje, {
    method: "POST", body: JSON.stringify({ me, cilj, b, zdaj }), headers: { "content-type": "application/json" } }));
}

/**
 * Durable Object ene naprave: njena prisotnost (SQLite, prezivi uspavanje), signali zanjo in rele do nje.
 * Rele uporablja WebSocket Hibernation API: mirujoce povezave ne porabljajo casa objekta.
 */
export class Koordinacija {
  constructor(ctx) {
    this.ctx = ctx;
    this.stanje = new Stanje();
    this.nalozeno = false;
    try { ctx.setWebSocketAutoResponse?.(new WebSocketRequestResponsePair("ping", "pong")); } catch {}
  }

  async prisotnost() {
    if (!this.nalozeno && this.ctx?.storage) {
      const r = await this.ctx.storage.get("prisotnost");
      if (r) this.stanje.prisotnost.set(r.device_id, r);
      this.nalozeno = true;
    }
  }

  async fetch(request) {
    const url = new URL(request.url);
    const dejanje = url.pathname.slice(1);
    await this.prisotnost();
    if (request.headers.get("upgrade") === "websocket") {
      const me = request.headers.get("x-safeer-me") || "";
      const par = new WebSocketPair();
      const napaka = this.rele(dejanje, me, url.searchParams.get("kanal") || "", par[1]);
      if (napaka) return json(napaka[0], napaka[1]);
      return new Response(null, { status: 101, webSocket: par[0] });
    }
    const { me, cilj, b, zdaj } = await request.json();
    this.stanje.pocisti(zdaj);
    if (dejanje === "objavi") {
      const odgovor = this.stanje.objavi(me, b, zdaj);
      if (odgovor[0] === 200) await this.ctx?.storage?.put("prisotnost", this.stanje.prisotnost.get(me));
      return json(...odgovor);
    }
    if (dejanje === "prevzemi") return json(...this.stanje.prevzemi(me));
    if (dejanje === "poisci") return json(...this.stanje.poisci(me, cilj));
    if (dejanje === "poslji") return json(...this.stanje.poslji(me, b, zdaj));
    return json(404, { error: "not_found" });
  }

  /** Sprejme WebSocket `ws` za dejanje releja; vrne [koda, telo] ob zavrnitvi ali null. */
  rele(dejanje, me, kanal, ws, zdaj = Math.floor(Date.now() / 1000)) {
    const ctx = this.ctx;
    if (dejanje === "poslusaj") {
      for (const star of ctx.getWebSockets("poslusa")) { try { star.close(1000, "zamenjan"); } catch {} }
      ctx.acceptWebSocket(ws, ["poslusa"]);
      return null;
    }
    if (dejanje === "povezi") {
      const r = [...this.stanje.prisotnost.values()][0];
      // Enak odgovor, ce huba ni ali naprava ni v njegovem krogu: tujec ne izve, ali hub obstaja.
      if (!r || r.expires_at <= zdaj || !r.allow.includes(me)) return [404, { error: "not_available" }];
      const poslusa = ctx.getWebSockets("poslusa")[0];
      if (!poslusa) return [404, { error: "not_available" }];
      if (ctx.getWebSockets("k:" + kanal).length) return [409, { error: "channel_in_use" }];
      if (ctx.getWebSockets("c").length >= NAJVEC_KANALOV) return [429, { error: "too_many_channels" }];
      ctx.acceptWebSocket(ws, ["c", "k:" + kanal]);
      poslusa.send(JSON.stringify({ type: "incoming", kanal, from: me }));
      return null;
    }
    if (dejanje === "sprejmi") {
      const odjemalec = ctx.getWebSockets("k:" + kanal).find((w) => ctx.getTags(w).includes("c"));
      if (!odjemalec || ctx.getWebSockets("k:" + kanal).length !== 1) return [404, { error: "no_channel" }];
      ctx.acceptWebSocket(ws, ["h", "k:" + kanal]);
      odjemalec.send("ready");
      return null;
    }
    return [404, { error: "not_found" }];
  }

  /** Bajti gredo nespremenjeni drugi strani istega kanala (TLS Safeer Linka od konca do konca). */
  webSocketMessage(ws, sporocilo) {
    const k = this.ctx.getTags(ws).find((t) => t.startsWith("k:"));
    if (!k) return;
    const druga = this.ctx.getWebSockets(k).find((w) => w !== ws);
    if (druga) { try { druga.send(sporocilo); } catch { this.zapri(k); } }
  }

  webSocketClose(ws) {
    const k = this.ctx.getTags(ws).find((t) => t.startsWith("k:"));
    if (k) this.zapri(k);
  }

  webSocketError(ws) { this.webSocketClose(ws); }

  zapri(k) {
    for (const w of this.ctx.getWebSockets(k)) { try { w.close(1000, "konec"); } catch {} }
  }
}

export default {
  async fetch(request, env) {
    if (env.SAFEER_GLOBAL_LINK_ENABLED !== "true" && new URL(request.url).pathname !== "/health") {
      return json(503, { error: "disabled" });
    }
    return usmeri((ime) => env.KOORDINACIJA.get(env.KOORDINACIJA.idFromName(ime)), request);
  },
};
