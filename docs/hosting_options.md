# Hosting options and pricing

A reference for where and how to host RegMap, from basement dev to production scale.
Prices are approximate as of mid-2025; verify on each provider's site before committing.

No em-dashes or en-dashes anywhere in this file (founder rule).

---

## Cloudflare Tunnel vs Cloudflare DNS proxy

**Cloudflare Tunnel** (`cloudflared` daemon) is for when you do not have a public IP or do not
want to open inbound ports (e.g. a home/basement server). The daemon dials outbound to
Cloudflare's edge; traffic flows back through the tunnel. No static IP needed.

**Cloudflare DNS proxy** (orange cloud in the DNS tab) is for any server that already has a
public IP (any VPS or cloud host). You point a DNS A record at the server IP and enable the
proxy. Cloudflare handles HTTPS, DDoS filtering, and caching in front of it. No daemon needed.

When you move from the basement to a VPS you switch from Tunnel to DNS proxy. Your Cloudflare
account and domain stay the same; only the routing changes.

---

## Basement setup (current / development)

| Item | Cost |
|---|---|
| Cloudflare Tunnel | Free (always-free tier) |
| Cloudflare DNS and proxy | Free |
| Custom domain (.com) | ~$10 to $15/year (Cloudflare Registrar is cheapest) |
| Hardware and electricity | Already paying |

**Total ongoing: ~$10 to $15/year.** Best choice while building and for early users.

For the full step-by-step walkthrough, see `docs/basement_hosting_guide.md`.

Steps:
1. Register domain at Cloudflare Registrar (or transfer an existing one).
2. Install `cloudflared` on the basement machine.
3. Run `cloudflared tunnel create regmap` and wire the tunnel to port 8010 (or whichever
   port uvicorn listens on).
4. Set `REGMAP_REQUIRE_AUTH=true`, `REGMAP_SECURE_COOKIES=true`, and all other production
   env vars before exposing the tunnel to the public internet.

---

## VPS providers (you manage the server)

Good choice when you want full control, predictable cost, and no vendor lock-in. You install
nginx as a reverse proxy in front of uvicorn, set up a systemd service, and manage your own
Postgres.

| Provider | Spec | Approx price/month |
|---|---|---|
| Hetzner CX22 | 2 vCPU, 4 GB RAM, 40 GB SSD | ~$4 to $5 |
| DigitalOcean Basic | 1 vCPU, 1 GB RAM, 25 GB SSD | ~$6 |
| DigitalOcean Basic | 1 vCPU, 2 GB RAM, 50 GB SSD | ~$12 |
| Linode / Akamai | 1 vCPU, 2 GB RAM | ~$12 |
| Vultr | 1 vCPU, 2 GB RAM | ~$12 |

**Minimum for RegMap:** 1 GB RAM. 2 GB is comfortable once Postgres is running alongside
uvicorn.

**Hetzner is the price/performance leader.** European data centres; CX22 covers early
production easily.

---

## Platform-as-a-service (they manage the runtime)

Easier to deploy (push code or a Docker image, they handle the rest) but costs more at scale
and gives less control.

| Provider | Plan | Approx price/month | Notes |
|---|---|---|---|
| Railway | Hobby | ~$5 + usage | Pay per CPU/RAM second; easy deploy |
| Fly.io | Pay as you go | ~$5 to $10 | Docker-native; closest to the k8s intent |
| Render | Starter web service | $7 | Sleeps after 15 min inactivity on free tier |
| Render | Standard | $25 | Always on, no sleep |

Fly.io is the smoothest path if you want to stay close to the Docker/k8s setup already
planned for RegMap without managing a raw server.

---

## Postgres database (when you graduate from SQLite)

RegMap's engine already supports Postgres via the `DATABASE_URL` env var. Switch when you
need concurrent writes or are on a VPS with multiple workers.

| Provider | Plan | Approx price/month | Notes |
|---|---|---|---|
| Supabase | Free tier | $0 | 500 MB limit; good for early production |
| Neon | Free tier | $0 | 0.5 GB; serverless Postgres |
| Railway | Hobby Postgres | ~$5 + usage | Stays close to the app on Railway |
| Render | Free Postgres | $0 | 90-day limit, then $7/month |
| DigitalOcean Managed Postgres | Basic | ~$15 | Managed backups, HA options |

---

## Why Bluehost (and shared hosting generally) does not fit

Bluehost shared plans run PHP and Apache. You cannot run a Python/FastAPI/uvicorn process on
them. Even their VPS tier is limited and not a natural environment for this stack. Do not use
shared hosting for RegMap.

---

## Recommended path by stage

| Stage | Setup | Approx cost |
|---|---|---|
| Building (now) | Basement + Cloudflare Tunnel + your domain | ~$12/year |
| Early launch (first ~100 users) | Hetzner CX22 + Cloudflare DNS proxy + Supabase free | ~$5 to $6/month |
| Growth | Hetzner CX32 (4 vCPU, 8 GB RAM) + managed Postgres | ~$25 to $30/month |

At early launch: switch Cloudflare from Tunnel to DNS proxy, point the A record at the Hetzner
IP, set `DATABASE_URL` to a Supabase/Neon connection string, and enable all production env vars
(`REGMAP_REQUIRE_AUTH`, `REGMAP_SECURE_COOKIES`, `REGMAP_ENFORCE_QUOTA`,
`REGMAP_ENFORCE_RATE_LIMIT`, `REGMAP_ADMIN_EMAILS`, `REGMAP_ANALYTICS_SALT`).

---

## Pre-launch env vars checklist

These are currently OFF in dev. Set all of them before the site is public.

```
REGMAP_REQUIRE_AUTH=true
REGMAP_SECURE_COOKIES=true
REGMAP_ENFORCE_QUOTA=true
REGMAP_ENFORCE_RATE_LIMIT=true
REGMAP_ADMIN_EMAILS=stetteh@xl.net
REGMAP_ANALYTICS_SALT=<long random string>
DATABASE_URL=<postgres connection string>
```

---

## Change log

- 2026-09-26: created from session discussion on hosting options and Cloudflare Tunnel.
