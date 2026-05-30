import { useEffect, useState } from 'react';
import { LOADING_MESSAGES } from '../reportCatalog';

export default function LoadingState({ reportName }) {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % LOADING_MESSAGES.length), 2200);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="card text-center py-16 max-w-lg mx-auto">
      <div className="h-2 rounded-full shimmer mb-6" />
      <p className="text-gold font-display text-xl mb-2">Generating {reportName}</p>
      <p className="text-graytown animate-pulse">{LOADING_MESSAGES[idx]}</p>
    </div>
  );
}
