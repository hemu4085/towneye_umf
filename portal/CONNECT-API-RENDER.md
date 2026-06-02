# Connect demo.towneye.ai using Render (instead of Railway)

You already use **Vercel** (frontend) and **Render** (backend) — same pattern here.

---

## What each service does

| Service | Role for TownEye demo |
|---------|------------------------|
| **Vercel** | Website at demo.towneye.ai ✅ already done |
| **Render** | Report API (addresses, reports, PDFs) ← Step 2 |
| **Tavily** | *Not hosting* — optional web-search API for data scrapers only; **not needed for the portal demo** |

**Tavily** (`tavily.com`) is an API key you add to `.env` when running scrapers/discovery agents. It does **not** replace Render for hosting the portal API.

---

## Step 1 — Push backend to GitHub (if not done)

```bash
cd ~/projects/fine_tuned_models/towneye_umf
chmod +x scripts/prepare_demo_data.sh
./scripts/prepare_demo_data.sh

git add backend/ core/ configs/arlington-ma/ reports/ demo-data/ \
  requirements.txt Dockerfile.api render.yaml .dockerignore

git commit -m "Add portal API for Render demo"
git push origin main
```

Confirm on GitHub: **`backend/main.py`** and **`demo-data/gold/arlington-ma/`** exist.

---

## Step 2 — Deploy API on Render (click by click)

### Option A — Blueprint (easiest if you see it)

1. Go to **[dashboard.render.com](https://dashboard.render.com)**
2. **New +** → **Blueprint**
3. Connect repo **`hemu4085/towneye`**
4. Render reads **`render.yaml`** and creates **towneye-api**
5. Click **Apply** → wait for deploy (~10–20 min first time)

### Option B — Manual Web Service (if no Blueprint)

1. **[dashboard.render.com](https://dashboard.render.com)** → **New +** → **Web Service**
2. Connect **GitHub** → repo **`hemu4085/towneye`**
3. Settings:

| Field | Value |
|-------|--------|
| **Name** | `towneye-api` |
| **Region** | Oregon (or closest to you) |
| **Branch** | `main` |
| **Runtime** | **Docker** |
| **Dockerfile Path** | `./Dockerfile.api` |
| **Instance type** | Free (or Starter for always-on demo) |

4. **Environment Variables** → Add:

| Key | Value |
|-----|--------|
| `PORTAL_PUBLIC_URL` | `https://demo.towneye.ai` |
| `CORS_ORIGINS` | `https://demo.towneye.ai,https://www.demo.towneye.ai,https://towneye.vercel.app` |
| `SUPPORTED_TOWNS` | `arlington-ma` |
| `GOLD_DATA_PATH` | `/data/gold` |
| `TOWNEYE_ENV` | `production` |

5. **Create Web Service** → wait for **Live**

6. Copy your URL at the top, e.g.  
   `https://towneye-api.onrender.com`

---

## Step 3 — Test the API

Open in browser:

```
https://towneye-api.onrender.com/api/health
```

(Use **your** Render URL.)

Expected: `{"status":"ok","towns":["arlington-ma"],...}`

**Free tier note:** First request after idle can take **30–60 seconds** (service wakes up). That’s normal on Render free.

---

## Step 4 — Connect Vercel

1. **[vercel.com](https://vercel.com)** → **towneye** project  
2. **Settings → Environment Variables** → Production:

| Name | Value |
|------|--------|
| `VITE_API_URL` | `https://towneye-api.onrender.com` |

(No trailing slash — use your real Render URL.)

3. **Deployments → Redeploy**

---

## Step 5 — Verify demo

1. **https://demo.towneye.ai** — offline banner should go away (after API wakes up once)  
2. Type `29 walnut` — suggestions appear  
3. **RE Agent** → **Buildability Brief** — report runs  

---

## Optional env vars (later)

| Key | When |
|-----|------|
| `ANTHROPIC_API_KEY` | Market / Pro Forma / Neighborhood reports |
| `TAVILY_API_KEY` | Only for running **scrapers** locally — not the live portal |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Render build fails | Logs → check `demo-data/gold/arlington-ma/parcel.parquet` is on GitHub |
| Health URL slow first time | Free tier cold start — wait 60s, retry |
| CORS error | Set `CORS_ORIGINS` on Render |
| Banner still on Vercel | Redeploy Vercel **after** adding `VITE_API_URL` |

---

## Your stack (same as before)

```
GitHub  →  Vercel (UI)  +  Render (API)
              ↓                ↓
         demo.towneye.ai    *.onrender.com
```

Railway is **not required** — Render does the same job.
