# TownEye Portal — Vercel + Render handoff

## Buildability report “Failed to fetch” (2026-06-02)

**Cause:** Vercel’s `/api` proxy times out (~60s) while Render free tier runs a heavy brief + PDF.

**Fixes on `main` (push + redeploy Render + Vercel):**

1. Pre-baked demo HTML: `demo-data/reports/arlington-ma/128.0-0003-0012.0/buildability.html` (29 Walnut) — instant on API.
2. Report POSTs call **Render directly** first (`frontend/src/api.js`) to skip Vercel timeout.
3. PDF export is best-effort; HTML preview still shows if PDF fails.

**Regenerate cache after gold data changes:**

```bash
.venv/bin/python scripts/generate_demo_report_cache.py
git add demo-data/reports/
```

---

## Status (2026-06-01)

| Layer | URL | Status |
|-------|-----|--------|
| Render API | https://towneye-umf.onrender.com | Live — `/api/health` OK |
| Vercel UI | https://towneye-umf.vercel.app | **404 — no production deploy** |
| Demo domain | https://demo.towneye.ai | Still on old `towneye` Vercel project |
| GitHub | https://github.com/hemu4085/towneye_umf | Demo gold data pushed (`1f156fb`) |

---

## Step 1 — Push pending fixes (WSL)

OOM fixes and slim demo data are in the working tree. Run:

```bash
cd ~/projects/fine_tuned_models/towneye_umf
sed -i 's/\r$//' scripts/prepare_demo_data.sh
./scripts/prepare_demo_data.sh arlington-ma   # excludes environmental-overlay (~14MiB)
git add backend/utils/parcel_lookup.py backend/services/report_availability.py \
  scripts/prepare_demo_data.sh demo-data/gold/arlington-ma/ frontend/src/pages/Home.jsx
git commit -m "Fix Render OOM: lightweight parcel resolve and slim demo data"
git push origin main
```

Wait for Render to rebuild (~5–10 min).

---

## Step 2 — Vercel production deploy

**Blocker:** WSL has no Vercel credentials (`vercel login` required).

1. Open https://vercel.com → project **towneye-umf**
2. **Settings → Git** → Connect **hemu4085/towneye_umf**, branch **main**
3. **Root Directory:** leave **empty** (repo root — `vercel.json` at root)
4. **Do not set** `VITE_API_URL` in Vercel (or remove it if present). Production uses same-origin `/api`; root `vercel.json` proxies to Render.
5. **Deployments → Create Deployment** (or push triggers auto-deploy)
6. Confirm build log shows `vite build` (~2s+, not 93ms)

**CLI alternative (after `vercel login` in WSL):**

```bash
cd ~/projects/fine_tuned_models/towneye_umf
vercel link --yes --project towneye-umf
vercel deploy --prod --yes
```

---

## Step 3 — Render CORS

In Render dashboard → **towneye-umf** → Environment:

```
CORS_ORIGINS=https://demo.towneye.ai,https://www.demo.towneye.ai,https://towneye-umf.vercel.app,https://towneye.vercel.app
```

(`render.yaml` already has this; sync dashboard if it differs.)

---

## Step 4 — Move demo.towneye.ai

After **towneye-umf.vercel.app** serves the portal:

1. Vercel → old **towneye** project → **Settings → Domains** → remove `demo.towneye.ai`
2. Vercel → **towneye-umf** → **Settings → Domains** → add `demo.towneye.ai`
3. Update DNS if prompted (usually automatic on same Vercel account)

---

## Step 5 — End-to-end test

1. https://towneye-umf.vercel.app — no “Report API is offline” banner
2. Address: `29 Walnut St, Arlington MA` — autocomplete shows matches
3. Role: **RE Agent** → **Buildability Brief** → HTML + PDF download

**API smoke test (WSL):**

```bash
curl -sS https://towneye-umf.onrender.com/api/health
curl -sS "https://towneye-umf.onrender.com/api/parcels/suggest?q=29%20Walnut&limit=3"
curl -sS -X POST https://towneye-umf.onrender.com/api/parcels/resolve \
  -H "Content-Type: application/json" \
  --data-raw '{"address":"29 Walnut St, Arlington MA"}'
curl -sS -X POST https://towneye-umf.onrender.com/api/reports/buildability \
  -H "Content-Type: application/json" \
  --data-raw '{"address":"29 Walnut St, Arlington MA","parcel_id":"128.0-0003-0012.0","town_slug":"arlington-ma"}' \
  | head -c 200
```

---

## Build settings (from root `vercel.json`)

| Setting | Value |
|---------|--------|
| Install | `cd frontend && npm install` |
| Build | `cd frontend && npm run build` |
| Output | `frontend/dist` |
| Node | 20.x (`frontend/.nvmrc`) |
