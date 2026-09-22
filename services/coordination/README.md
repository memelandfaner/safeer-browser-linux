# Safeer Coordination (link.safeer.si)

Cloudflare Worker z enim Durable Objectom (SQLite, brezplacen nacrt Workers: 100.000 zahtev na dan).
Pomaga seznanjenim napravam, da se najdejo zunaj domacega omrezja (Global Mesh): prisotnost in kratki
signali. Nikoli kljuci ali vsebina. Podpis zahtev s kljucem naprave (ECDSA P-256 iz kroga zaupanja),
brez skupne skrivnosti. Prisotnost in signale vidijo samo naprave s seznama `allow` (krog zaupanja).

- Test: `node test.mjs` (Node 22; na Node 18 `node --experimental-global-webcrypto test.mjs`)
- Postavitev: `npx wrangler deploy` v tej mapi (zeton Cloudflare z dovoljenjem za Workers)
- Vklop: `SAFEER_GLOBAL_LINK_ENABLED = "true"` v `wrangler.toml` - sele po preizkusu cez locena omrezja
- STUN: `stun:stun.cloudflare.com:3478` (brezplacno); TURN: Cloudflare Realtime TURN (1000 GB/mesec brezplacno)
