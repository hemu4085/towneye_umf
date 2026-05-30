# Fix demo.towneye.ai 404 on Vercel

Your build log shows the problem:

```
Build Completed in /vercel/output [93ms]
Skipping cache upload because no files were prepared
```

**93ms = Vercel did not run `npm install` or `vite build`.** Nothing was deployed → 404.

---

## Cause

One of these is true:

1. **GitHub repo `hemu4085/towneye` does not contain the portal** (`frontend/`, `vercel.json`) at commit `392b005`
2. **Vercel project settings** override `vercel.json` (wrong Root Directory or Framework)

This workspace (`towneye_umf`) has the portal code. It must be **pushed to `hemu4085/towneye`**.

---

## Step 1 — Push portal code to GitHub

From this project (WSL):

```bash
cd ~/projects/fine_tuned_models/towneye_umf

# If not already linked to your GitHub repo:
git remote add origin git@github.com:hemu4085/towneye.git
# OR: git remote set-url origin git@github.com:hemu4085/towneye.git

git add frontend/ vercel.json backend/ portal/ scripts/ core/ configs/ reports/ requirements.txt Dockerfile.api railway.toml .env.example
git status   # review what will be committed — do NOT commit .env or data/gold

git commit -m "Add TownEye portal for demo.towneye.ai"
git push origin main
```

If `hemu4085/towneye` already has other files, merge or push to a branch and open a PR.

**Verify on GitHub:** you should see `frontend/package.json` and `vercel.json` at the repo root.

---

## Step 2 — Fix Vercel project settings

Vercel → **towneye** project → **Settings → General**

| Setting | Value |
|---------|--------|
| **Root Directory** | *(leave empty — repo root)* |
| **Framework Preset** | **Other** (or let `vercel.json` control it) |
| **Node.js Version** | 20.x |

**Settings → Build & Development** — click **Override** only if wrong; prefer **vercel.json** at repo root:

- Install: `npm install --prefix frontend`
- Build: `npm run build --prefix frontend`
- Output: `frontend/dist`

**Alternative (simpler):** set **Root Directory** to `frontend`, Framework **Vite**, Output **dist**. Then `frontend/vercel.json` handles SPA routing.

---

## Step 3 — Environment variable (after API is live)

**Settings → Environment Variables → Production:**

| Name | Value |
|------|--------|
| `VITE_API_URL` | Your Railway API URL (add later when API is deployed) |

Redeploy after adding.

---

## Step 4 — Redeploy and verify build log

**Deployments → Redeploy**

A **good** build log looks like:

```
Running "npm install --prefix frontend"
...
Running "npm run build --prefix frontend"
vite v5.x building for production...
✓ built in 8s
```

**Not** 93ms with "no files were prepared".

Then open **https://demo.towneye.ai** — you should see the TownEye address screen.

---

## Step 5 — API (reports still need this)

Vercel only hosts the UI. Reports need a backend + gold data (Railway). See [DEPLOY-VERCEL.md](./DEPLOY-VERCEL.md).

Until `VITE_API_URL` is set, the UI loads but report generation will fail.

---

## Quick checklist

- [ ] `frontend/` and `vercel.json` exist on GitHub `main`
- [ ] Vercel Root Directory = empty **or** `frontend` (with matching settings)
- [ ] Build log shows `vite build` (~5–30 seconds)
- [ ] demo.towneye.ai shows TownEye portal (not 404)
- [ ] `VITE_API_URL` set when API is ready
