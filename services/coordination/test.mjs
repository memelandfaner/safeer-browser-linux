// node test.mjs - preizkus koordinacije brez omrezja (pravi ECDSA P-256 podpisi, DER kot Java).
import assert from "node:assert/strict";
import { webcrypto as c, createSign, generateKeyPairSync } from "node:crypto";
import { Koordinacija, usmeri, idIzKljuca, NAJVEC_SIGNALOV } from "./worker.mjs";

function naprava() {
  const { publicKey, privateKey } = generateKeyPairSync("ec", { namedCurve: "P-256" });
  const spki = publicKey.export({ type: "spki", format: "der" }).toString("base64");
  return { spki, privateKey };
}
async function zahteva(n, metoda, pot, telo = "", cas = Math.floor(Date.now() / 1000), pokvari = false) {
  const izv = Buffer.from(await c.subtle.digest("SHA-256", new TextEncoder().encode(telo))).toString("hex");
  const s = createSign("SHA256"); s.update(`${metoda}\n${pot}\n${cas}\n${izv}`);
  let podpis = s.sign(n.privateKey).toString("base64");   // DER, kot Java SHA256withECDSA
  if (pokvari) podpis = podpis.slice(0, -4) + (podpis.endsWith("AAAA") ? "BBBB" : "AAAA");
  return new Request("https://link.safeer.si" + pot, { method: metoda, body: metoda === "POST" ? telo : undefined,
    headers: { "x-safeer-key": n.spki, "x-safeer-time": String(cas), "x-safeer-signature": podpis } });
}
// Imenik Durable Objectov kot v Cloudflare: en objekt na ime (id naprave).
const objekti = new Map();
const imenik = (ime) => { if (!objekti.has(ime)) objekti.set(ime, new Koordinacija()); return objekti.get(ime); };
const tel = naprava(), tv = naprava(), tujec = naprava(), tujTel = naprava();
const idTel = await idIzKljuca(tel.spki), idTv = await idIzKljuca(tv.spki), idTujTel = await idIzKljuca(tujTel.spki), idTujec = await idIzKljuca(tujec.spki);
const klic = async (...a) => { const r = await usmeri(imenik, await zahteva(...a)); return [r.status, await r.json()]; };

assert.equal((await usmeri(imenik, new Request("https://link.safeer.si/health"))).status, 200);
assert.equal((await klic(tel, "GET", "/v1/signals", "", undefined, true))[0], 401, "pokvarjen podpis");
assert.equal((await klic(tel, "GET", "/v1/signals", "", Math.floor(Date.now() / 1000) - 600))[0], 401, "star cas");
assert.equal((await klic(tel, "POST", "/v1/presence", JSON.stringify({ candidate_hints: ["lan:192.168.0.143"], allow: [idTv] })))[0], 200);
assert.equal((await klic(tv, "POST", "/v1/presence", JSON.stringify({ allow: [idTel], ttl: "x" })))[0], 400);
assert.equal((await klic(tv, "POST", "/v1/presence", JSON.stringify({ allow: [idTel] })))[0], 200);
// TV je v krogu telefona: vidi prisotnost in poslje signal
let [k, t] = await klic(tv, "GET", `/v1/presence?device_id=${idTel}`);
assert.deepEqual(t.presence.candidate_hints, ["lan:192.168.0.143"]);
assert.equal((await klic(tv, "POST", "/v1/signal", JSON.stringify({ to: idTel, payload: { offer: "sdp" } })))[0], 202);
// tujec ne vidi nicesar in njegov signal ne pride
[k, t] = await klic(tujec, "GET", `/v1/presence?device_id=${idTel}`); assert.equal(t.presence, null);
await klic(tujec, "POST", "/v1/signal", JSON.stringify({ to: idTel, payload: { spam: 1 } }));
[k, t] = await klic(tel, "GET", "/v1/signals");
assert.deepEqual(t.signals, [{ from: idTv, payload: { offer: "sdp" } }]);
assert.deepEqual((await klic(tel, "GET", "/v1/signals"))[1].signals, []);
// meje
assert.equal((await klic(tv, "POST", "/v1/signal", JSON.stringify({ to: idTv, payload: {} })))[0], 400, "sebi");
for (let i = 0; i < NAJVEC_SIGNALOV; i++) await klic(tv, "POST", "/v1/signal", JSON.stringify({ to: idTel, payload: i }));
assert.equal((await klic(tv, "POST", "/v1/signal", JSON.stringify({ to: idTel, payload: 1 })))[0], 429);
// drug uporabnik (tujec + njegov telefon) vidi samo svoje naprave, mojih ne
assert.equal((await klic(tujTel, "POST", "/v1/presence", JSON.stringify({ allow: [idTujec] })))[0], 200);
assert.ok((await klic(tujec, "GET", `/v1/presence?device_id=${idTujTel}`))[1].presence, "svojo napravo vidi");
assert.equal((await klic(tujec, "GET", `/v1/presence?device_id=${idTv}`))[1].presence, null, "moje ne vidi");
assert.equal((await klic(tel, "GET", `/v1/presence?device_id=${idTujTel}`))[1].presence, null, "jaz ne vidim njegove");
// vsaka naprava je svoj objekt: ni skupnega seznama vseh naprav
assert.ok([...objekti.keys()].every((k) => /^n-[0-9a-f]{16}$/.test(k)));
assert.equal(objekti.get(idTel).stanje.prisotnost.size, 1);
// potek
const s = objekti.get(idTel).stanje; s.pocisti(Math.floor(Date.now() / 1000) + 1000); assert.equal(s.prisotnost.size, 0);
console.log("Safeer Coordination (Worker): vse v redu");

// ---- rele: lazni ctx (Hibernation API) in lazne vticnice
class LazniWs { constructor(i) { this.i = i; this.prejeto = []; this.zaprt = false; } send(m) { this.prejeto.push(m); } close() { this.zaprt = true; } }
class LazniCtx {
  constructor() { this.ws = []; }
  acceptWebSocket(ws, tags) { this.ws.push([ws, tags]); }
  getWebSockets(tag) { return this.ws.filter(([w, t]) => !w.zaprt && (!tag || t.includes(tag))).map(([w]) => w); }
  getTags(ws) { return (this.ws.find(([w]) => w === ws) || [null, []])[1]; }
}
{
  const hub = new Koordinacija(new LazniCtx());
  const zdaj = Math.floor(Date.now() / 1000);
  hub.stanje.objavi("n-00000000000000aa", { allow: [idTel] }, zdaj);          // hub dovoli telefon
  const k = "0123456789abcdef0123456789abcdef";
  assert.deepEqual(hub.rele("povezi", idTel, k, new LazniWs("t0"), zdaj)[0], 404, "hub ne poslusa");
  const poslusa = new LazniWs("p"); assert.equal(hub.rele("poslusaj", "", "", poslusa, zdaj), null);
  assert.equal(hub.rele("povezi", idTujec, k, new LazniWs("x"), zdaj)[0], 404, "tujec ne pride skozi");
  const tel = new LazniWs("tel"); assert.equal(hub.rele("povezi", idTel, k, tel, zdaj), null);
  assert.deepEqual(JSON.parse(poslusa.prejeto[0]), { type: "incoming", kanal: k, from: idTel });
  assert.equal(hub.rele("povezi", idTel, k, new LazniWs("dvojnik"), zdaj)[0], 409, "kanal enkrat");
  const h = new LazniWs("hub"); assert.equal(hub.rele("sprejmi", "", k, h, zdaj), null);
  assert.deepEqual(tel.prejeto, ["ready"]);
  assert.equal(hub.rele("sprejmi", "", k, new LazniWs("h2"), zdaj)[0], 404, "kanal ze sprejet");
  const bajti = new Uint8Array([22, 3, 1]).buffer;                               // TLS ClientHello ...
  hub.webSocketMessage(tel, bajti); assert.equal(h.prejeto[0], bajti);
  hub.webSocketMessage(h, "odgovor"); assert.equal(tel.prejeto[1], "odgovor");
  hub.webSocketClose(tel); assert.ok(h.zaprt, "konec ene strani zapre drugo");
  const nov = new LazniWs("p2"); hub.rele("poslusaj", "", "", nov, zdaj); assert.ok(poslusa.zaprt, "en poslusalec");
}
console.log("Safeer rele: vse v redu");
