# Wipe demo.towneye.ai → Next.js `web/` (investor freeze)

Replaces the old Vite `frontend/` portal on Vercel with the Next.js MVP in `web/`.
API stays on Render.

| Piece | Host | Notes |
|-------|------|--------|
| UI | **Vercel** → `https://demo.towneye.ai` | Root Directory **must** be `web` |
| API | **Render** → `https://towneye-umf.onrender.com` | `Dockerfile.api` + Gold in image |

**Freeze:** tag `Towneye_investor_ready_demo_07172026` (`9683fd0` + later deploy commits).

---

## 1. Push this branch / tag to GitHub

Deploy from `cursor/build-towenye-mvp-2636` (or merge to `main` if Production Branch is `main`).

```bash
git push origin HEAD
git push origin Towneye_investor_ready_demo_07172026
```

---

## 2. Render API (redeploy freeze)

1. [dashboard.render.com](https://dashboard.render.com) → service **towneye-umf** (or `towneye-api`)
2. **Settings → Build & Deploy → Branch** → same branch as the freeze (or `main` after merge)
3. **Manual Deploy → Deploy latest commit**
4. Confirm env:

| Variable | Value |
|----------|--------|
| `PORTAL_PUBLIC_URL` | `https://demo.towneye.ai` |
| `CORS_ORIGINS` | `https://demo.towneye.ai,https://www.demo.towneye.ai,https://towneye.vercel.app,https://towneye-umf.vercel.app` |
| `PORTAL_SKIP_PDF` | `true` |
| `TOWNEYE_ENV` | `production` |
| `GOLD_DATA_PATH` | `/data/gold` |
| `ANTHROPIC_API_KEY` | (secret, optional for richer LLM reports) |

5. Health: `https://towneye-umf.onrender.com/api/health`

---

## 3. Vercel — wipe Vite, point at Next `web/`

1. [vercel.com](https://vercel.com) → project that owns **demo.towneye.ai** (usually **towneye**)
2. **Settings → General → Root Directory** → set to **`web`** → Save  
   (This is the wipe: Vercel stops building `frontend/`.)
3. **Settings → Git → Production Branch** → branch that has this freeze
4. **Settings → Environment Variables** (Production + Preview):

| Name | Value |
|------|--------|
| `NEXT_PUBLIC_API_URL` | `https://towneye-umf.onrender.com` |

   Remove obsolete Vite vars if present (`VITE_API_URL`).

5. **Deployments → … → Redeploy** (clear cache if offered)
6. Domains: keep `demo.towneye.ai` + `www.demo.towneye.ai` on this project

---

## 4. Verify

1. Hard-refresh `https://demo.towneye.ai` — should show the Next sidebar MVP (not the old Vite portal)
2. Select **5-7 Belknap St** / parcel `008.0-0001-0010.0` → Homeowner / Neighborhood / Zoning
3. Confirm reports hit Render (Network tab → `towneye-umf.onrender.com`)

---

## Rollback

1. Vercel Root Directory → empty / `.` and restore old `vercel.json` that builds `frontend/`
2. Or redeploy a prior Vercel deployment from the Deployments list
3. Render: redeploy previous successful deploy
