import { useEffect } from 'react';

export interface SeriesStore {
  push: (key: string, value: number) => void;
  read: (key: string) => number[];
  /** Snapshot reference is stable until a new sample is pushed for `key`. */
  subscribe: (cb: () => void) => () => void;
}

const MAX_SAMPLES = 150;

/**
 * A single shared empty array. read() returns this for unknown keys so
 * useSyncExternalStore keeps seeing the same reference and does not loop.
 * push() never mutates this; it always creates a new array.
 */
const EMPTY: number[] = [];

export function createSeriesStore(): SeriesStore {
  const data: Record<string, number[]> = {};
  const listeners = new Set<() => void>();
  return {
    push(key, value) {
      const prev = data[key] ?? EMPTY;
      const next = prev.length >= MAX_SAMPLES
        ? [...prev.slice(1), value]
        : [...prev, value];
      data[key] = next;
      listeners.forEach((cb) => cb());
    },
    read(key) {
      return data[key] ?? EMPTY;
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