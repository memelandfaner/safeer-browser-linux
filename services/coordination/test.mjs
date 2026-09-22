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
