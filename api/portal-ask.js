/**
 * Vercel serverless proxy for property Q&A.
 * Server-to-server call to Render avoids browser 401 on cross-origin / rewrite issues.
 */
const RENDER_ASK_URL =
  process.env.RENDER_ASK_URL || 'https://towneye-umf.onrender.com/api/reports/ask';

module.exports = async function handler(req, res) {
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
    const ct = upstream.headers.get('content-type') || 'application/json';
    res.status(upstream.status);
    res.setHeader('Content-Type', ct);
    return res.send(text);
  } catch (err) {
    return res.status(502).json({
      detail: err?.message || 'Upstream API unavailable',
    });
  }
};
