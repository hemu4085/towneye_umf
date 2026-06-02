# Connect demo.towneye.ai to the Report API

The banner means **Vercel has the UI only**. Reports need a backend + one env var.

**Using Render instead of Railway?** → see **[CONNECT-API-RENDER.md](./CONNECT-API-RENDER.md)** (recommended if you already use Render).

---

## Overview (30–45 min, one time)

```
demo.towneye.ai  →  Vercel (frontend)  — done ✅
Render / Railway →  FastAPI + gold data  — you do this ⬜
VITE_API_URL     →  links them           — you do this ⬜
```

---

## Step 1 — Push backend code to GitHub

In **WSL**:

```bash
cd ~/projects/fine_tuned_models/towneye_umf

# Package arlington demo data for the API (~run once)
chmod +x scripts/prepare_demo_data.sh
./scripts/prepare_demo_data.sh

# Stage API + demo data (do NOT add data/gold or .env)
git add backend/ core/ configs/arlington-ma/ configs/lexington-ma/ configs/somerville-ma/ \
  reports/ demo-data/ requirements.txt Dockerfile.api railway.toml .dockerignore \
  frontend/src/

git commit -m "Add portal API for Railway and connect frontend to backend"
git push origin main
```

Check GitHub: you should see `backend/main.py` and `demo-data/gold/arlington-ma/`.

---

## Step 2 — Deploy API on Railway

1. Go to **[railway.app](https://railway.app)** → sign in with GitHub  
2. **New Project** → **Deploy from GitHub repo** → choose **`hemu4085/towneye`**  
3. Railway reads `railway.toml` + `Dockerfile.api` automatically  
4. Wait for deploy → **Settings → Variables** → add:

| Variable | Value |
|----------|--------|
| `PORTAL_PUBLIC_URL` | `https://demo.towneye.ai` |
| `CORS_ORIGINS` | `https://demo.towneye.ai,https://www.demo.towneye.ai,https://towneye.vercel.app` |
| `SUPPORTED_TOWNS` | `arlington-ma` |
| `ANTHROPIC_API_KEY` | *(optional, for Market/Pro Forma reports)* |

5. **Settings → Networking → Generate Domain**  
6. Copy the URL, e.g. `https://towneye-production-xxxx.up.railway.app`

**Test in browser:**

```
https://YOUR-RAILWAY-URL.up.railway.app/api/health
```

Should return: `{"status":"ok", ...}`

---

## Step 3 — Connect Vercel to Railway

1. **[vercel.com](https://vercel.com)** → **towneye** project  
2. **Settings → Environment Variables**  
3. Add (Production):

| Name | Value |
|------|--------|
| `VITE_API_URL` | `https://YOUR-RAILWAY-URL.up.railway.app` |

No trailing slash.

4. **Deployments → Redeploy** (must rebuild so Vite embeds the URL)

---

## Step 4 — Verify demo

1. Open **https://demo.towneye.ai** — banner should **disappear**  
2. Type `29 walnut` — address suggestions appear  
3. Pick **RE Agent** → **Buildability Brief** — report generates  

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Banner still shows | Hard refresh; confirm `VITE_API_URL` set and Vercel **redeployed after** adding it |
| CORS error in browser console | Add `CORS_ORIGINS` on Railway (Step 2) |
| Health OK but parcel not found | Re-run `./scripts/prepare_demo_data.sh`, commit `demo-data/`, push, Railway redeploys |
| Railway build fails | Check Railway build logs; ensure `demo-data/gold/arlington-ma/parcel.parquet` exists on GitHub |

---

## Costs

- **Vercel** — free tier for frontend  
- **Railway** — ~$5/month hobby credit after trial (enough for demo)
