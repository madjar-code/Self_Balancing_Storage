import { useEffect } from 'react';

export interface SeriesStore {
  push: (key: string, value: number) => void;
  read: (key: string) => number[];
  /** Returns the same reference until a new sample is appended for `key`. */
  subscribe: (cb: () => void) => () => void;
}

const MAX_SAMPLES = 150;

export function createSeriesStore(): SeriesStore {
  const data: Record<string, number[]> = {};
  const listeners = new Set<() => void>();
  return {
    push(key, value) {
      const buf = data[key] ?? [];
      buf.push(value);
      if (buf.length > MAX_SAMPLES) buf.shift();
      data[key] = buf;
      listeners.forEach((cb) => cb());
    },
    read(key) {
      return data[key] ?? [];
    },
    subscribe(cb) {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
  };
}

/** Push `value` into series `key` once per render where `value` changed. */
export function useTimeSeriesSampler(store: SeriesStore, key: string, value: number | undefined) {
  useEffect(() => {
    if (typeof value === 'number') store.push(key, value);
  }, [store, key, value]);
}