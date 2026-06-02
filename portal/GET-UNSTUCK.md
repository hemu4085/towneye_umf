# Get unstuck — demo.towneye.ai in 3 steps

You are here because Vercel shows **404**. Two things were wrong:

1. **Portal code was never pushed to GitHub** (Vercel builds from GitHub, not your laptop)
2. **Build was broken** — fixed now (`frontend/src/api.js`)

---

## Step 1 — Push portal to GitHub (one time)

Open **WSL Ubuntu** terminal and paste this whole block:

```bash
cd ~/projects/fine_tuned_models/towneye_umf

git add frontend/ vercel.json portal/

git commit -m "Add TownEye portal for demo.towneye.ai"

git push origin main
```

If Git asks for login, use your GitHub username + a **Personal Access Token** (not your password).

**Check:** Open https://github.com/hemu4085/towneye — you should see a `frontend` folder.

---

## Step 2 — Redeploy on Vercel (one click)

1. Go to https://vercel.com → your **towneye** project  
2. Click **Deployments**  
3. Click **⋯** on the latest deploy → **Redeploy**  
4. Wait ~1–2 minutes  

**Check the build log** — it should say `vite build` and take **several seconds**, not 93ms.

---

## Step 3 — Open the demo

Go to **https://demo.towneye.ai**

You should see: **TownEye** + address box + role buttons.

---

## What about reports?

The **UI** works after Step 2. **Generating reports** needs an API server (not Vercel) — that’s a **later step**. For the demo UI, Steps 1–3 are enough.

When you’re ready for reports, we’ll add Railway + `VITE_API_URL`.

---

## Build failed on Vercel (vite / node_modules error)

If you see `Cannot find module vite/dist/node/cli.js`:

**Cause:** `frontend/node_modules` was accidentally committed to GitHub. Vercel then breaks when reinstalling.

**Fix** — run in WSL:

```bash
cd ~/projects/fine_tuned_models/towneye_umf
git rm -r --cached frontend/node_modules
git add .gitignore vercel.json frontend/package.json frontend/.nvmrc frontend/package-lock.json
git commit -m "Fix Vercel build: remove node_modules from git, pin Node 20"
git push origin main
```

Then **Redeploy** on Vercel.

---

## If something fails

| Problem | What to do |
|---------|------------|
| `git push` rejected | Tell me the error message |
| Build still 93ms on Vercel | Settings → Root Directory → set to `frontend`, Framework → Vite |
| Still 404 | Send a screenshot of the new build log |
| Blank page | Browser hard refresh (Ctrl+Shift+R) |

You only need **Step 1 + Step 2** right now.
