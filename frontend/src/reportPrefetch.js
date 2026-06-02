/**
 * In-memory report fetch cache — Promises cannot be stored in router history state.
 */

let pending = null;

export function startReportPrefetch(cacheKey, promise) {
  pending = { cacheKey, promise };
}

export function consumeReportPrefetch(cacheKey) {
  if (!pending || pending.cacheKey !== cacheKey) return null;
  const { promise } = pending;
  pending = null;
  return promise;
}

export function reportCacheKey(reportId, parcelId) {
  return `${reportId}:${parcelId}`;
}
