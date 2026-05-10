import { ChunkInfo } from '../api/types';

const STATE_ORDER: Record<string, number> = {
  open: 0,
  sealed: 1,
  persisted: 2,
};

/**
 * Returns a copy of `chunks` sorted with open chunks first, then sealed,
 * then persisted. Within a state, newest (highest ts_min) first.
 */
export function sortChunksOpenFirst(chunks: ChunkInfo[]): ChunkInfo[] {
  return [...chunks].sort((a, b) => {
    const sa = STATE_ORDER[a.state] ?? 99;
    const sb = STATE_ORDER[b.state] ?? 99;
    if (sa !== sb) return sa - sb;
    return b.ts_min - a.ts_min;
  });
}
