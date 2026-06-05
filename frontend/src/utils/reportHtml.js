/** Extract renderable fragments from backend HTML report documents. */

export function extractReportStyles(html) {
  if (!html) return '';
  const blocks = [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/gi)];
  return blocks.map((m) => m[1]).join('\n');
}

export function extractReportBody(html) {
  if (!html) return '';
  const match = html.match(/<body[^>]*>([\s\S]*)<\/body>/i);
  return match ? match[1].trim() : html;
}
