# Server Setup

Production deployment guide for Backoffice.

## Architecture Overview

```
Internet → Cloudflare (DNS + SSL) → Cloudflare Tunnel → Nginx (localhost) → Backend + Frontend
```

Traffic never touches your server's public ports. Cloudflare Tunnel creates an outbound-only encrypted connection, so no firewall inbound rules are needed.

---

## Prerequisites

- A server or Mac mini running macOS or Linux (Apple Silicon works well)
- Python 3.12+ and Git installed
- [Cloudflare account](https://cloudflare.com) with a domain
- [Supabase](https://supabase.com) account (managed PostgreSQL) — or self-host PostgreSQL
- [Cloudflare R2](https://developers.cloudflare.com/r2/) bucket (S3-compatible object storage)

---

## 1. Database — Supabase

1. Create a new Supabase project at [app.supabase.com](https://app.supabase.com)
2. Go to **Project Settings → Database**
3. Copy the connection string (URI format):
   ```
   postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres
   ```
4. Replace `postgresql://` with `postgresql+asyncpg://` for async use:
   ```
   DATABASE_URL=postgresql+asyncpg://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres
   ```

---

## 2. Storage — Cloudflare R2

1. Go to **Cloudflare Dashboard → R2**
2. Create a bucket named `backoffice`
3. Go to **Manage R2 API Tokens** and create a token with **Object Read & Write** on your bucket
4. Note:
   - Account ID (visible in R2 overview URL: `dash.cloudflare.com/<account-id>/r2`)
   - Access Key ID
   - Secret Access Key

R2 endpoint format:
```
https://<account-id>.r2.cloudflarestorage.com
```

---

## 3. Environment Configuration

```bash
cd backoffice
cp .env.production.example .env.production
```

Edit `.env.production`:

```bash
# Database (Supabase)
DATABASE_URL=postgresql+asyncpg://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres

# Storage (Cloudflare R2)
S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
S3_ACCESS_KEY=<r2-access-key-id>
S3_SECRET_KEY=<r2-secret-access-key>
S3_BUCKET=backoffice
S3_REGION=auto

# Auth
JWT_SECRET=<generate with: openssl rand -hex 32>

# App URL (used in setup links)
API_BASE_URL=https://backoffice.yourdomain.com

# CORS (comma-separated)
CORS_ORIGINS=https://backoffice.yourdomain.com
```

---

## 4. Server Setup

Run the setup script. This creates a Python virtualenv, installs dependencies, runs migrations, and installs a launchd service.

```bash
scripts/setup-production.sh
```

This script:
1. Creates `backend/.venv` and installs backend dependencies
2. Installs the `acct` CLI
3. Runs Alembic migrations against your production database
4. Installs a launchd service (`~/Library/LaunchAgents/com.backoffice.server.plist`) that auto-starts the server on login

### Manual service control

```bash
# Start
launchctl load ~/Library/LaunchAgents/com.backoffice.server.plist

# Stop
launchctl unload ~/Library/LaunchAgents/com.backoffice.server.plist

# Check status
launchctl list | grep backoffice
```

---

## 5. DNS — Cloudflare Tunnel

Cloudflare Tunnel routes traffic from your domain to `localhost` without opening inbound firewall ports.

### Install cloudflared

```bash
# macOS
brew install cloudflared

# Or download from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
```

### Authenticate and create tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create backoffice
```

This creates a tunnel credentials file at `~/.cloudflared/<tunnel-id>.json`.

### Configure tunnel

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: <tunnel-id>
credentials-file: /Users/<you>/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: backoffice.yourdomain.com
    service: http://localhost:8080
  - service: http_status:404
```

The production Docker Compose exposes Nginx on `127.0.0.1:8080` (configurable via `BACKOFFICE_PORT`).

### Create DNS record

```bash
cloudflared tunnel route dns backoffice backoffice.yourdomain.com
```

This creates a `CNAME` record in Cloudflare pointing to your tunnel.

### Start tunnel as service

```bash
sudo cloudflared service install
```

---

## 6. Docker Compose (Production)

The production compose file runs Backend + Frontend + Nginx + Cloudflare Tunnel as containers. It reads from `.env.production`.

```bash
docker compose -f docker-compose.production.yml up -d
```

Services:
- `backend` — FastAPI on port 8000 (internal)
- `frontend` — Next.js on port 3000 (internal)
- `nginx` — Reverse proxy on `127.0.0.1:8080`
- `cloudflared` — Tunnel to Cloudflare

The `cloudflared` service reads tunnel credentials from `~/.cloudflared` (or the path set in `CLOUDFLARED_CONFIG_DIR`).

---

## 7. SSL

SSL is handled automatically by Cloudflare. Your server only serves HTTP to localhost; Cloudflare terminates TLS and proxies to your tunnel. No certificate management is needed.

---

## 8. First Run

After the server is running, initialize the system:

```bash
acct init --api-url https://backoffice.yourdomain.com
```

Follow the [Onboarding guide](onboarding.md) to complete setup.

---

## 9. Updating

```bash
scripts/update.sh
```

This script:
1. Pulls latest code from `main`
2. Installs updated backend dependencies
3. Runs Alembic migrations
4. Restarts the launchd service

---

## 10. Monitoring and Logs

Logs are written to `./logs/` (mounted into the backend container).

```bash
# Tail live logs
tail -f logs/backoffice.log

# Backend container logs
docker compose -f docker-compose.production.yml logs -f backend

# All services
docker compose -f docker-compose.production.yml logs -f
```

API health check:

```bash
curl https://backoffice.yourdomain.com/health
```
