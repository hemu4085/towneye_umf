# Deploy TownEye to demo.towneye.ai with GitHub + Vercel

TownEye is a **Vite frontend + FastAPI backend**. Your Vercel domains are already set up:

| Domain | Role |
|--------|------|
| `demo.towneye.ai` | Primary demo URL |
| `www.demo.towneye.ai` | Alias |
| `towneye.vercel.app` | Vercel default URL |

**Recommended stack:**

| Part | Host | URL |
|------|------|-----|
| Frontend | **Vercel** (you have this) | `https://demo.towneye.ai` |
| API | **Railway** (or Render) | `https://your-api.up.railway.app` |

---

## Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "TownEye portal demo"
git remote add origin https://github.com/YOUR_USER/towneye_umf.git
git push -u origin main
```

> **Gold data:** `data/gold/` is gitignored (large files). You will attach it on Railway via a volume (Step 3).

---

## Step 2 — Deploy the API on Railway

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Select your `towneye_umf` repository
3. Railway detects `railway.toml` + `Dockerfile.api` automatically
4. **Settings → Variables** — add:

| Variable | Value |
|----------|--------|
| `PORTAL_PUBLIC_URL` | `https://demo.towneye.ai` |
| `CORS_ORIGINS` | `https://demo.towneye.ai,https://www.demo.towneye.ai,https://towneye.vercel.app` |
| `ANTHROPIC_API_KEY` | your key (for Market / Pro Forma / Neighborhood) |
| `SUPPORTED_TOWNS` | `arlington-ma,lexington-ma,somerville-ma` |
| `GOLD_DATA_PATH` | `/data/gold` |

5. **Settings → Networking → Generate Domain** — copy the public URL (e.g. `https://towneye-api-production.up.railway.app`)

### Attach gold data (Railway volume)

1. **Project → Add → Volume** — mount at `/data/gold`
2. Upload your local gold parquets (one-time):

```bash
# From your dev machine (with Railway CLI installed)
railway login
railway link
railway run bash
# Then from another terminal, copy files into the volume — or use rsync/scp to the running service
```

**Simpler demo option:** copy `data/gold/arlington-ma/` to the volume with only the files needed for the demo (parcel, zoning, etc.).

3. Confirm API health:

```bash
curl https://YOUR-RAILWAY-URL.up.railway.app/api/health
```

---

## Step 3 — Vercel (your existing project)

You already have **demo.towneye.ai** connected. Confirm:

1. Vercel project → **Settings → Git** — repo is this `towneye_umf` project (with `frontend/` + `vercel.json`)
2. **Settings → Environment Variables** (Production):

| Variable | Value |
|----------|--------|
| `VITE_API_URL` | `https://YOUR-RAILWAY-URL.up.railway.app` |

3. **Redeploy** after pushing portal code to GitHub

Every `git push` to `main` redeploys automatically.

---

## Step 4 — Domains (already done)

Your domains should already show under **Settings → Domains**:

- `demo.towneye.ai`
- `www.demo.towneye.ai`
- `towneye.vercel.app`

No change needed unless DNS shows errors in Vercel.

---

## Step 5 — Verify the demo

1. Open **https://demo.towneye.ai**
2. Enter `29 Walnut St, Arlington MA`
3. Pick a role → click **Buildability Brief**
4. **Share Link** should copy a working PDF URL
5. LLM reports need `ANTHROPIC_API_KEY` set on Railway

---

## How it works

```
Browser → demo.towneye.ai (Vercel, static React)
       → VITE_API_URL/api/* (Railway, FastAPI)
       → /data/gold/*.parquet (Railway volume)
```

- **Share Link** uses the Railway PDF URL (via `VITE_API_URL`)
- **CORS** on the API allows `demo.towneye.ai` and `towneye.vercel.app`

---

## Local development (unchanged)

```bash
./scripts/start_portal.sh
```

Uses Vite proxy to `localhost:8000` — no `VITE_API_URL` needed locally.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Reports fail / parcel not found | Gold data missing on Railway volume — check `GOLD_DATA_PATH` |
| CORS error in browser | Set `CORS_ORIGINS` on Railway (see Step 2) |
| LLM reports unavailable | Add `ANTHROPIC_API_KEY` on Railway |
| Vercel build fails | Ensure root `vercel.json` exists; Node 18+ in Vercel settings |

---

## Alternative: Vercel-only (not recommended)

Vercel serverless cannot run this API reliably (large pandas/parquet deps, gold data size, PDF disk writes). Use Railway (or Render/Fly) for the API.

See also [DEPLOY.md](./DEPLOY.md) for single-VPS deployment with Caddy.
