# PDEUE 4-Domain Air-Gapped HTTPS Deployment Runbook (AWS Lightsail)

**Target Host:** `pdeue-ring1-paper` (`44.200.6.195`)  
**Authoritative Branch:** `ring1-alpha`  
**Reverse Proxy:** `caddy:2-alpine` (`pdeue-caddy`, automatic Let's Encrypt TLS on ports `80` / `443`, `128m` RAM limit)  
**Compose Stack:** `deploy/docker-compose.paper.yml` + `docker-compose.domains.yml`

---

## Architecture & Invariants Preserved

| Domain | Plane | Upstream / Behavior | Blocked Routes |
| :--- | :--- | :--- | :--- |
| `www.narratixai.org` | Canonical Redirect | `301` -> `https://narratixai.org{uri}` | N/A |
| `narratixai.org` | Family Social & Heritage | `pdeue-paper-api:8000` (`/`, `/home`, `/community`, `/community/*`, `/static/*`, `/api/v1/portal/planes`, `/api/v1/portal/community/*`, `/health`); Jitsi Meet camera/mic/display-capture allowed for `https://meet.jit.si` | `403` on `/member*`, `/advisor*`, `/dashboard*`, `/admin*`, `/lineage*`, `/api/v1/ledger*`, `/api/v1/governance*`, `/api/v1/operator*`, etc. |
| `narratixai.info` | PDEUE University | `/` -> `302 /companion`; proxies `/companion*`, `/static/*`, `/api/v1/portal/planes`, `/api/v1/portal/companion*`, `/api/v1/manuals*`, `/api/v1/lexicon*`, `/health` | `403` on financial, operational, and admin routes |
| `vault.narratixai.io` | Personal Account & Custodial Vault | `/` -> `302 /member`; proxies `/member*`, `/advisor*`, `/lineage/*`, `/static/*`, `/api/v1/portal/*`, `/api/v1/member/*`, `/api/v1/advisor/*`, `/api/v1/lineage/*`, `/api/v1/lexicon*`, `/api/v1/onboarding/*`, `/health` | `403` on `/dashboard*`, `/admin*`, `/api/v1/operator*`, `/api/v1/workspace*`, `/api/v1/accounting*` |
| `admin.narratixai.io` | Executive & Technical Operations | `/` -> `302 /dashboard`; proxies `/dashboard*`, `/admin/*`, `/static/*`, `/api/v1/*`, `/health` | Fail-closed `404` outside allowlist |
| `narratixai.net` | Standalone IFAS Accounting Air-Gap | Static zero-CDN HTML (`/srv/ifas/index.html`) — **ZERO** `reverse_proxy` to PDEUE | `403` on `/api/*`, `/dashboard*`, `/admin*`, `/member*`, `/advisor*`, `/lineage*` |

- **Gate G1 Fail-Closed Paper Defaults Preserved:** `PDEUE_VENUE_MODE=paper`, `PDEUE_LIVE_TRADING_ENABLED=false`, `PDEUE_GOVERNANCE_MODE=EXECUTIVE_COMMAND`, `PDEUE_GATE_G1_STATUS=HOLD_OBSERVATIONS_ONLY`.
- **Collector & Data Integrity:** `pdeue-l2-collector`, `/var/lib/pdeue/data`, and `/var/lib/pdeue/tapes` are untouched by the overlay.
- **Dark-by-Default Backend:** `pdeue-api` (`container_name: pdeue-paper-api`) stays bound to `127.0.0.1:8000` (do **not** override `PDEUE_HTTP_PORT=80`).

---

## Step 1 — AWS Lightsail Firewall (Networking Tab)

1. Open the AWS Lightsail Console -> Instances -> **`pdeue-ring1-paper`** (`44.200.6.195`).
2. Select the **Networking** tab -> **IPv4 Firewall**.
3. Confirm or add the following inbound TCP rules:
   - **SSH (`22`)** — restricted to your operator IP (recommended).
   - **HTTP (`80`)** — TCP, open (`0.0.0.0/0`) — required for Let's Encrypt ACME HTTP-01 challenges and automatic HTTP -> HTTPS redirects.
   - **HTTPS (`443`)** — TCP, open (`0.0.0.0/0`) — click **+ Add rule** -> Application: **HTTPS**, Protocol: **TCP**, Port: **443** -> **Create**.
4. Ensure port **`8000`** is **NOT** publicly exposed; all external traffic enters exclusively via `pdeue-caddy` on `80`/`443`.

---

## Step 2 — Route 53 DNS `A` Records

Create or verify the following **Type `A`** records (TTL `300`) pointing to `44.200.6.195` in their respective Route 53 hosted zones:

| Hosted Zone | Record Name | Type | Value |
| :--- | :--- | :--- | :--- |
| `narratixai.org` | `narratixai.org` | `A` | `44.200.6.195` |
| `narratixai.org` | `www.narratixai.org` | `A` | `44.200.6.195` |
| `narratixai.info` | `narratixai.info` | `A` | `44.200.6.195` |
| `narratixai.io` | `vault.narratixai.io` | `A` | `44.200.6.195` |
| `narratixai.io` | `admin.narratixai.io` | `A` | `44.200.6.195` |
| `narratixai.net` | `narratixai.net` | `A` | `44.200.6.195` |

Verify propagation from your workstation before launching Caddy (so Let's Encrypt issuance succeeds on the first attempt):

```bash
for host in narratixai.org www.narratixai.org narratixai.info vault.narratixai.io admin.narratixai.io narratixai.net; do
  printf "%-22s -> %s\n" "$host" "$(dig +short A "$host" | tr '\n' ' ')"
done
```

Every host should return `44.200.6.195`.

---

## Step 3 — Update & Launch on `pdeue-ring1-paper`

SSH into `pdeue-ring1-paper`, `cd` into the repository checkout (e.g., `/opt/pdeue` or `~/PDEUE_Project_GeminiBuild`), and run this single-line command. It creates persistent TLS directories under `/var/lib/pdeue/caddy`, pulls `ring1-alpha`, preserves `/var/lib/pdeue/data` and `/var/lib/pdeue/tapes`, and brings up `pdeue-paper-api` + `pdeue-caddy` without disrupting `pdeue-l2-collector`:

```bash
sudo mkdir -p /var/lib/pdeue/caddy/data /var/lib/pdeue/caddy/config && git fetch origin ring1-alpha && git checkout ring1-alpha && git pull --ff-only origin ring1-alpha && docker compose -f deploy/docker-compose.paper.yml -f docker-compose.domains.yml up -d --build
```

> **Zero-Restart Option for `pdeue-l2-collector` Mid-Soak:**  
> If `pdeue-l2-collector` is mid-capture and you only want to update `pdeue-api` (`pdeue-paper-api`) and start `pdeue-caddy` without touching the collector container:
>
> ```bash
> docker compose -f deploy/docker-compose.paper.yml -f docker-compose.domains.yml up -d --no-deps --build pdeue-api pdeue-caddy
> ```

Confirm all three containers are running and healthy:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker logs --tail 30 pdeue-caddy
```

Expected containers:
- `pdeue-paper-api` (`healthy`, `127.0.0.1:8000->8000/tcp`)
- `pdeue-l2-collector` (`healthy`, uninterrupted)
- `pdeue-caddy` (`Up`, `0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp`)

---

## Step 4 — Post-Launch HTTPS & Air-Gap Verification Checklist

Run the following checks from any external workstation (allow 15–30 seconds after first start for Caddy to complete Let's Encrypt certificate issuance):

### 4.1 TLS & Canonical Redirects Across All Hosts

```bash
# 1. Apex www -> 301 canonical redirect
curl -I https://www.narratixai.org/home
# Expect: HTTP/2 301  |  location: https://narratixai.org/home

# 2. Family Social & Heritage Plane
curl -I https://narratixai.org/home
# Expect: HTTP/2 200  |  strict-transport-security + x-content-type-options: nosniff

# 3. PDEUE University Plane
curl -I https://narratixai.info/
# Expect: HTTP/2 302  |  location: /companion
curl -I https://narratixai.info/companion
# Expect: HTTP/2 200

# 4. Personal Account & Custodial Vault Plane
curl -I https://vault.narratixai.io/
# Expect: HTTP/2 302  |  location: /member
curl -I https://vault.narratixai.io/member
# Expect: HTTP/2 200

# 5. Executive & Technical Operations Plane
curl -I https://admin.narratixai.io/
# Expect: HTTP/2 302  |  location: /dashboard
curl -I https://admin.narratixai.io/dashboard
# Expect: HTTP/2 200

# 6. Standalone IFAS Air-Gap Plane (static HTML, zero PDEUE proxy)
curl -I https://narratixai.net/
# Expect: HTTP/2 200  |  content-type: text/html
```

### 4.2 Host-Level Air-Gap Negative Checks (Must Return `403` / `404`)

```bash
# Financial & admin routes MUST be blocked on narratixai.org
curl -I https://narratixai.org/dashboard          # Expect: HTTP/2 403
curl -I https://narratixai.org/member             # Expect: HTTP/2 403
curl -I https://narratixai.org/api/v1/ledger      # Expect: HTTP/2 403
curl -I https://narratixai.org/api/v1/governance  # Expect: HTTP/2 403
curl -I https://narratixai.org/api/v1/operator    # Expect: HTTP/2 403

# Financial & admin routes MUST be blocked on narratixai.info
curl -I https://narratixai.info/dashboard         # Expect: HTTP/2 403
curl -I https://narratixai.info/member            # Expect: HTTP/2 403

# Executive & tech admin routes MUST be blocked on vault.narratixai.io
curl -I https://vault.narratixai.io/dashboard     # Expect: HTTP/2 403
curl -I https://vault.narratixai.io/admin/tech    # Expect: HTTP/2 403

# PDEUE API & trading routes MUST be blocked on narratixai.net
curl -I https://narratixai.net/dashboard          # Expect: HTTP/2 403
curl -I https://narratixai.net/api/v1/health      # Expect: HTTP/2 403
```

### 4.3 Gate G1 Fail-Closed Paper Mode & Plane Config Verification

```bash
# Confirm fail-closed paper mode & Gate G1 HOLD_OBSERVATIONS_ONLY
curl -s https://narratixai.org/health | jq .
# Expect: "venue_mode": "paper", "paper_mode": true, "live_trading_enabled": false, "gate_g1_status": "HOLD_OBSERVATIONS_ONLY"

# Confirm all 5 production plane URLs resolve via plane_routing.py
curl -s https://narratixai.org/api/v1/portal/planes | jq '{routing_mode, doorways}'
# Expect: "routing_mode": "multi_domain_air_gapped" with narratixai.org / .info / vault.narratixai.io / admin.narratixai.io / narratixai.net
```

### 4.4 Confirm `pdeue-l2-collector` & Tape Capture Remain Intact

```bash
cat /var/lib/pdeue/tapes/collector_heartbeat.json | jq '{status, timestamp_utc, consecutive_errors, snapshots_total, synthetic_fills_present}'
```
