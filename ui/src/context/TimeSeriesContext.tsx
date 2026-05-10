import { createContext, ReactNode, useContext, useMemo, useSyncExternalStore } from 'react';
import { createSeriesStore, SeriesStore } from '../lib/useTimeSeries';

const TSCtx = createContext<SeriesStore | null>(null);

export function TimeSeriesProvider({ children }: { children: ReactNode }) {
  const store = useMemo(createSeriesStore, []);
  return <TSCtx.Provider value={store}>{children}</TSCtx.Provider>;
}

export function useSeriesStore(): SeriesStore {
  const store = useContext(TSCtx);
  if (!store) throw new Error('TimeSeriesProvider missing');
  return store;
}

/** Subscribe to a series; re-renders the caller when new samples arrive. */
export function useSeries(key: string): number[] {
  const store = useSeriesStore();
  return useSyncExternalStore(
    (cb) => store.subscribe(cb),
    () => store.read(key),
  );
}