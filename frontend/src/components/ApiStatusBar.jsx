export default function ApiStatusBar({ online, checking, onRetry }) {
  if (checking) {
    return (
      <p className="text-center text-sm text-graytown mt-3 animate-pulse">
        Connecting to TownEye API…
      </p>
    );
  }
  if (online) {
    return null;
  }
  return (
    <div className="text-center mt-3">
      <p className="text-sm text-amber-300">
        API is temporarily unavailable. Reports may be slow until connected.
      </p>
      <button type="button" onClick={onRetry} className="text-gold text-sm underline mt-1">
        Retry connection
      </button>
    </div>
  );
}
