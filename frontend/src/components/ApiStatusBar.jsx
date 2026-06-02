export default function ApiStatusBar({ online, checking, onRetry }) {
  if (checking) {
    return (
      <p className="text-center text-sm text-graytown mt-3 animate-pulse">
        Connecting to TownEye API…
      </p>
    );
  }
  if (online) {
    return (
      <p className="text-center text-sm text-green-400/90 mt-3">
        API connected — type an address (e.g. 29 walnut) for suggestions
      </p>
    );
  }
  return (
    <div className="text-center mt-3">
      <p className="text-sm text-amber-300">
        API is waking up (free-tier cloud). Suggestions and reports may be slow.
      </p>
      <button type="button" onClick={onRetry} className="text-gold text-sm underline mt-1">
        Retry connection
      </button>
    </div>
  );
}
