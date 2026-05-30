# TownEye Portal

Full-stack web app for generating Massachusetts property intelligence reports.

## Quick start

### One command (WSL / Linux)

```bash
chmod +x scripts/start_portal.sh
./scripts/start_portal.sh
```

### Manual setup

#### 1. Backend (from repo root)

```bash
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY for Market / Pro Forma / Neighborhood reports

.venv/bin/pip install fastapi uvicorn httpx python-dotenv email-validator anthropic

# From repo root:
.venv/bin/uvicorn backend.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Production

| Workflow | Guide |
|----------|--------|
| **GitHub + Vercel** (recommended) | [DEPLOY-VERCEL.md](./DEPLOY-VERCEL.md) — UI on Vercel, API on Railway |
| Single VPS + Caddy | [DEPLOY.md](./DEPLOY.md) |

```bash
./scripts/start_portal_prod.sh   # local production preview on :8000
```

## User flow

1. **Address + user type** — enter a MA address and pick your role
2. **Pick report** — click a report card; the parcel is resolved and generation starts immediately
3. **Report page: HTML + PDF** — inline preview, download PDF, share link

Test address: `29 Walnut St, Arlington MA`

## Reports

| Report | Backend | LLM |
|--------|---------|-----|
| Buildability Brief | `BuildabilityBriefGenerator` | No |
| Zoning Summary | Gold parquets | No |
| Risk & Constraints | Wraparound layers | No |
| Market Snapshot | Gold + Claude Sonnet 4 | Yes |
| Pro Forma | Envelope + Claude | Yes |
| Neighborhood Intel | Claude | Yes |
| Lender Pack | Bundled | No |

## Architecture

- `backend/` — FastAPI, wraps existing TownEye engine
- `frontend/` — React + Tailwind + Vite
- Gold data: `data/gold/{town_slug}/`
- PDFs: `reports/output/`
