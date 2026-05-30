# Deploy TownEye Portal to towneye.ai

Single-server setup: FastAPI serves the built React app and `/api` on one port. Put **Caddy** or **nginx** in front for HTTPS.

## 1. DNS (at your domain registrar)

Point **towneye.ai** to your demo server:

| Type | Name | Value |
|------|------|--------|
| A | `@` | Your server public IP |
| A | `www` | Same IP (optional) |

If you use Cloudflare, proxy (orange cloud) is fine — enable SSL “Full”.

## 2. Server setup (Ubuntu)

```bash
# On the demo VPS
git clone <your-repo> towneye_umf
cd towneye_umf

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY for LLM reports

chmod +x scripts/*.sh
./scripts/start_portal_prod.sh
```

The app listens on **0.0.0.0:8000** and serves:

- `https://towneye.ai/` — portal UI  
- `https://towneye.ai/api/...` — API  
- `https://towneye.ai/api/files/...` — PDF downloads  

Verify: `curl https://towneye.ai/api/health`

## 3. HTTPS with Caddy (recommended)

Install [Caddy](https://caddyserver.com/docs/install), then:

```bash
sudo tee /etc/caddy/Caddyfile <<'EOF'
towneye.ai, www.towneye.ai {
    reverse_proxy localhost:8000
}
EOF

sudo systemctl reload caddy
```

Caddy obtains and renews Let’s Encrypt certificates automatically.

## 4. Run as a service (systemd)

```bash
sudo tee /etc/systemd/system/towneye-portal.service <<EOF
[Unit]
Description=TownEye Portal Demo
After=network.target

[Service]
Type=simple
User=myunix
WorkingDirectory=/home/myunix/projects/fine_tuned_models/towneye_umf
Environment=TOWNEYE_ENV=production
Environment=SERVE_FRONTEND=true
Environment=PORTAL_PUBLIC_URL=https://towneye.ai
ExecStart=/home/myunix/projects/fine_tuned_models/towneye_umf/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now towneye-portal
```

Build the frontend before first start:

```bash
./scripts/build_portal.sh
```

## 5. Local development (unchanged)

```bash
./scripts/start_portal.sh
```

- UI: http://localhost:5173  
- API: http://localhost:8000  

## Environment

| Variable | Demo default | Purpose |
|----------|--------------|---------|
| `PORTAL_PUBLIC_URL` | `https://towneye.ai` | Public URL (health check, CORS) |
| `TOWNEYE_ENV` | `production` | Enables static frontend serving |
| `SERVE_FRONTEND` | `true` | Serve `frontend/dist` from FastAPI |
| `CORS_ORIGINS` | auto from `PORTAL_PUBLIC_URL` | Extra allowed origins |

## Demo checklist

- [ ] DNS A record for `towneye.ai`  
- [ ] HTTPS reverse proxy (Caddy/nginx)  
- [ ] `ANTHROPIC_API_KEY` in `.env` (for Market / Pro Forma / Neighborhood)  
- [ ] Gold data present under `data/gold/`  
- [ ] Test: `29 Walnut St, Arlington MA` → Buildability Brief  
