# Basement hosting guide

Step-by-step instructions for running RegMap from a home/basement server and exposing it
to the internet via a Cloudflare Tunnel. No static IP or open router ports required.

No em-dashes or en-dashes anywhere in this file (founder rule).

Last updated: 2026-09-26.

---

## What you will end up with

- RegMap running 24/7 on a machine in your home.
- A real domain name (e.g. `regmap.io`) served over HTTPS.
- Cloudflare as the front door: handles HTTPS certificates, DDoS protection, and caching.
- No open ports on your router. Cloudflare Tunnel creates an outbound-only encrypted
  connection, so your home IP is never exposed.

---

## Prerequisites

Before you start, have the following ready:

- A machine that can stay on 24/7 (a dedicated PC, mini PC, or old laptop works).
  Minimum: 2 GB RAM, 20 GB free disk, a wired ethernet connection.
- A Cloudflare account (free). Sign up at https://cloudflare.com.
- A domain name registered at Cloudflare Registrar (cheapest) or transferred to Cloudflare
  so its DNS is managed there.
- Python 3.11+ installed on the host machine.
- Git installed on the host machine.
- The RegMap repo cloned onto the host machine.

---

## Step 1: Set up your domain in Cloudflare

1. Log in to the Cloudflare dashboard (dash.cloudflare.com).
2. Click **Add a site**, enter your domain, and follow the prompts.
   - If you registered the domain elsewhere, Cloudflare will give you two nameservers to
     set at your registrar. Point them there and wait for propagation (up to 24 hours).
   - If you are buying a new domain, use **Cloudflare Registrar** (under Account > Registrar)
     to keep everything in one place.
3. Once the domain shows **Active** in the dashboard, move to Step 2.

---

## Step 2: Install cloudflared on the host machine

`cloudflared` is the daemon that creates and maintains the tunnel.

### Windows

1. Download the latest Windows installer from:
   https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
   (direct link: `cloudflared-windows-amd64.msi`)
2. Run the installer. It adds `cloudflared` to your PATH.
3. Open PowerShell and verify:
   ```
   cloudflared --version
   ```

### Linux (if your basement machine runs Linux)

```bash
# Debian/Ubuntu
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg > /dev/null
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install cloudflared
```

---

## Step 3: Authenticate cloudflared with your Cloudflare account

Run this command (on the host machine, in any terminal):

```
cloudflared tunnel login
```

A browser window opens. Log in to your Cloudflare account and select the domain you added
in Step 1. Cloudflare issues a certificate that is saved to:
- Windows: `C:\Users\<you>\.cloudflared\cert.pem`
- Linux: `~/.cloudflared/cert.pem`

---

## Step 4: Create the tunnel

```
cloudflared tunnel create regmap
```

This creates a tunnel named `regmap` and saves a credentials file:
- Windows: `C:\Users\<you>\.cloudflared\<tunnel-id>.json`
- Linux: `~/.cloudflared/<tunnel-id>.json`

Note the tunnel ID printed in the output. You will need it in the next step.

---

## Step 5: Write the tunnel config file

Create a file called `config.yml` in the `.cloudflared` folder:
- Windows path: `C:\Users\<you>\.cloudflared\config.yml`
- Linux path: `~/.cloudflared/config.yml`

Contents (replace `<tunnel-id>` and `yourdomain.com` with your values):

```yaml
tunnel: <tunnel-id>
credentials-file: C:\Users\<you>\.cloudflared\<tunnel-id>.json

ingress:
  - hostname: yourdomain.com
    service: http://127.0.0.1:8010
  - hostname: www.yourdomain.com
    service: http://127.0.0.1:8010
  - service: http_status:404
```

On Linux, replace the credentials-file path with `/home/<you>/.cloudflared/<tunnel-id>.json`.

This tells the tunnel to forward all requests for your domain to port 8010 on localhost,
which is where uvicorn runs RegMap.

---

## Step 6: Create the DNS record in Cloudflare

This points your domain at the tunnel (not at an IP address):

```
cloudflared tunnel route dns regmap yourdomain.com
cloudflared tunnel route dns regmap www.yourdomain.com
```

Check the Cloudflare DNS dashboard and confirm both records show a CNAME pointing to
`<tunnel-id>.cfargotunnel.com` with the orange cloud (proxy) enabled.

---

## Step 7: Set your production environment variables

Before starting the app for real users, set these variables. The easiest way on Windows
is to add them to your PowerShell profile or create a `.env`-style launcher script.

```
REGMAP_REQUIRE_AUTH=true
REGMAP_SECURE_COOKIES=true
REGMAP_ENFORCE_QUOTA=true
REGMAP_ENFORCE_RATE_LIMIT=true
REGMAP_ADMIN_EMAILS=stetteh@xl.net
REGMAP_ANALYTICS_SALT=<a long random string, generate once and keep it>
DATABASE_URL=sqlite:///./regmap.db
```

For `REGMAP_ANALYTICS_SALT`, generate a random string once and save it somewhere safe
(your password manager). It only needs to stay the same across restarts; it is not a login
password.

Leave `DATABASE_URL` as SQLite for now. When you are ready for Postgres (e.g. on Supabase
or Neon), replace it with the Postgres connection string from that provider.

---

## Step 8: Start RegMap

In a terminal, from the repo root:

```powershell
cd C:\Users\User\regmap-platform
$env:REGMAP_REQUIRE_AUTH      = "true"
$env:REGMAP_SECURE_COOKIES    = "true"
$env:REGMAP_ENFORCE_QUOTA     = "true"
$env:REGMAP_ENFORCE_RATE_LIMIT= "true"
$env:REGMAP_ADMIN_EMAILS      = "stetteh@xl.net"
$env:REGMAP_ANALYTICS_SALT    = "your-long-random-string"
python -m uvicorn main:app --host 127.0.0.1 --port 8010
```

Leave this terminal open (or set it up as a Windows service in Step 9).

---

## Step 9: Start the tunnel

In a second terminal:

```
cloudflared tunnel run regmap
```

Leave this terminal open too. Now visit `https://yourdomain.com` in a browser. You should
see RegMap served over HTTPS. Cloudflare issues and renews the TLS certificate automatically.

---

## Step 10: Make both processes start automatically on boot (Windows)

So you do not need to remember to start them manually after a reboot.

### Option A: Task Scheduler (simplest)

1. Open **Task Scheduler** (search for it in the Start menu).
2. Create two tasks: one for uvicorn and one for cloudflared.
3. For each task:
   - Trigger: **At startup**
   - Action: **Start a program**
   - Run whether or not user is logged on: checked
   - Run with highest privileges: checked

For the uvicorn task, the program is `python` and the arguments are:
```
-m uvicorn main:app --host 127.0.0.1 --port 8010
```
Set the **Start in** field to `C:\Users\User\regmap-platform`.
Add the env vars under **Environment variables** in the task settings (or use a wrapper `.bat`
script that sets them and calls python).

For the cloudflared task, the program is `cloudflared` and the arguments are:
```
tunnel run regmap
```

### Option B: NSSM (Non-Sucking Service Manager)

A cleaner way to run both as proper Windows services with auto-restart on crash.

1. Download NSSM from https://nssm.cc and put `nssm.exe` somewhere in your PATH.
2. In an admin PowerShell:
   ```
   nssm install RegMapApp python
   nssm set RegMapApp AppParameters "-m uvicorn main:app --host 127.0.0.1 --port 8010"
   nssm set RegMapApp AppDirectory "C:\Users\User\regmap-platform"
   nssm set RegMapApp AppEnvironmentExtra REGMAP_REQUIRE_AUTH=true REGMAP_SECURE_COOKIES=true REGMAP_ENFORCE_QUOTA=true REGMAP_ENFORCE_RATE_LIMIT=true REGMAP_ADMIN_EMAILS=stetteh@xl.net REGMAP_ANALYTICS_SALT=your-random-string
   nssm start RegMapApp

   nssm install CloudflaredTunnel cloudflared
   nssm set CloudflaredTunnel AppParameters "tunnel run regmap"
   nssm start CloudflaredTunnel
   ```
3. Both services now start automatically on boot and restart themselves if they crash.

---

## Ongoing maintenance

| Task | How often | What to do |
|---|---|---|
| Update RegMap | As needed | `git pull` in the repo, then restart the RegMapApp service |
| Check tunnel health | Occasional | Cloudflare dashboard > Zero Trust > Networks > Tunnels |
| Monitor logs | As needed | NSSM writes logs to `C:\nssm\<service>\`. Task Scheduler logs are in Event Viewer. |
| Rotate analytics salt | Never (unless compromised) | Change the env var and restart the app |
| Upgrade cloudflared | Every few months | Re-run the MSI installer, restart the service |

---

## Moving to a VPS later

When you are ready to move off the basement machine:

1. Provision a Hetzner CX22 (or equivalent) running Ubuntu 24 LTS.
2. Clone the repo onto the server. Install Python 3.11+, set up a virtual environment.
3. Set the same env vars (via `/etc/environment` or a systemd unit file).
4. Run RegMap with `uvicorn main:app --host 127.0.0.1 --port 8010` behind an nginx
   reverse proxy.
5. In the Cloudflare DNS dashboard, delete the CNAME tunnel record and add an **A record**
   pointing to the server's public IP. Enable the orange cloud (proxy). HTTPS is handled
   by Cloudflare automatically.
6. Stop and delete the Cloudflare Tunnel (`cloudflared tunnel delete regmap`). You no
   longer need it.

The app itself is identical on either machine. Only the Cloudflare routing changes.

---

## Troubleshooting quick reference

| Symptom | Check |
|---|---|
| Site shows Cloudflare 1033 error | Tunnel is not running. Start `cloudflared tunnel run regmap`. |
| Site shows 502 Bad Gateway | uvicorn is not running on port 8010. Start the app. |
| HTTPS cert error | DNS record is not proxied (orange cloud off). Enable it in Cloudflare DNS. |
| Changes to the site not showing | Old cached HTML. Hard refresh (Ctrl+Shift+R). Cloudflare cache can be purged in the dashboard under Caching > Configuration > Purge Everything. |
| Admin dashboard shows "access only" | Not signed in, or email not in REGMAP_ADMIN_EMAILS. Check the env var and restart the app. |

---

## Change log

- 2026-09-26: created.
