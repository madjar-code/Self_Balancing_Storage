import { useEffect, useState } from 'react';

export function useSSE(url: string, onEvent: (data: string) => void) {
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource(url);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (ev) => onEvent(ev.data);
    /**
     * The backend uses sse-starlette which emits named events (event: decision,
     * event: burst, event: tier_change). We listen on those too.
     */
    for (const name of ['decision', 'burst', 'tier_change']) {
      es.addEventListener(name, (ev) => onEvent((ev as MessageEvent).data));
    }
    return () => {
      es.close();
      setConnected(false);
    };
  }, [url, onEvent]);

  return { connected };
}