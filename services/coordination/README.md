# Safeer Coordination (link.safeer.si)

Cloudflare Worker, vsaka naprava ima svoj Durable Object (SQLite, brezplacen nacrt: 100.000 zahtev na dan).
Pomaga seznanjenim napravam, da se najdejo zunaj domacega omrezja (Global Mesh): prisotnost in kratki
signali. Nikoli kljuci ali vsebina. Podpis zahtev s kljucem naprave (ECDSA P-256 iz kroga zaupanja),
brez skupne skrivnosti.

Global Link je za vsakega uporabnika samo njegov krog zaupanja: prisotnost naprave vidi in ji signal
poslje samo naprava s seznama `allow`, ki ga objavi naprava sama (clani njenega kroga v Safeer Linku).
Drug uporabnik vidi samo svoje naprave; o tujih ne izve niti, ali obstajajo. Skupnega seznama vseh
naprav ni (en Durable Object na napravo).

- Test: `node test.mjs` (Node 22; na Node 18 `node --experimental-global-webcrypto test.mjs`)
- Postavitev: `npx wrangler deploy` v tej mapi (zeton Cloudflare z dovoljenjem za Workers)
- Vklop: `SAFEER_GLOBAL_LINK_ENABLED = "true"` v `wrangler.toml` - sele po preizkusu cez locena omrezja
- STUN: `stun:stun.cloudflare.com:3478` (brezplacno); TURN: Cloudflare Realtime TURN (1000 GB/mesec brezplacno)
