/**
 * POST /api/property-ask — property Q&A (not proxied by vercel.json).
 * Server-side call to Render avoids browser 401 on /api/reports/ask rewrite.
 */
const RENDER_ASK_URL =
  process.env.RENDER_ASK_URL || 'https://towneye-umf.onrender.com/api/reports/ask';

async function handler(req, res) {
  res.setHeader('Content-Type', 'application/json');

  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Accept');
    return res.status(204).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ detail: 'Method Not Allowed' });
  }

  let body = req.body;
  if (typeof body === 'string') {
    try {
      body = JSON.parse(body);
    } catch {
      return res.status(400).json({ detail: 'Invalid JSON body' });
    }
  }

  const headers = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    'User-Agent': 'TownEye-Vercel-PropertyAsk/1.0',
  };
  const bearer = process.env.RENDER_SERVICE_BEARER || '';
  if (bearer) {
    headers.Authorization = `Bearer ${bearer}`;
  }

  try {
    const upstream = await fetch(RENDER_ASK_URL, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });
    const text = await upstream.text();
    const trimmed = text.trim();

    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        const data = JSON.parse(trimmed);
        return res.status(upstream.status).json(data);
      } catch {
        /* fall through */
      }
    }

    return res.status(502).json({
      detail:
        `Property Q&A upstream returned HTTP ${upstream.status} (non-JSON). ` +
        'Redeploy Render from latest main and confirm /api/reports/ask exists.',
      upstream_status: upstream.status,
    });
  } catch (err) {
    return res.status(502).json({
      detail: err?.message || 'Could not reach Render API for property Q&A',
    });
  }
}

module.exports = handler;
module.exports.config = { maxDuration: 60 };
