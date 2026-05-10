export interface EngineState {
  write_rate: number;
  burst_ratio: number;
  is_burst: boolean;
  memory_pressure: number;
  n_chunks: number;
  n_sealed: number;
  n_indexed: number;
}

export interface ChunkInfo {
  chunk_id: string;
  tier: 'hot' | 'cold';
  state: 'open' | 'sealed' | 'persisted';
  count: number;
  ts_min: number;
  ts_max: number;
  services: string[];
  indexes: string[];
  indexes_on_disk: string[];
  temperature: number;
}

export interface IndexInfo {
  index_id: string;
  chunk_id: string;
  type: 'hash' | 'skip' | 'bloom' | 'unknown';
  field: string;
  op: string | null;
  memory_bytes: number;
  usage: number;
  last_used: number | null;
  status: 'active' | 'dropped';
  dropped_at?: number;
  prior_usage?: number;
}

export interface TopPredicate {
  field: string;
  op: string;
  value: unknown;
  freq: number;
}

export type DecisionType =
  | 'build_index' | 'drop_index' | 'restore_index'
  | 'promote' | 'demote' | 'evict_heavy_index';

export interface DecisionEvent {
  type: 'decision' | 'tier_change' | 'burst';
  ts: number;
  action?: DecisionType;
  chunk_id?: string;
  predicate?: { field: string; op: string };
  index_type?: string;
  index_id?: string;
  from?: string;
  to?: string;
  state?: 'enter' | 'exit';
  ratio?: number;
}

export interface QueryResult {
  results: Array<{
    ts: number;
    service: string;
    level: string;
    msg: string;
    fields: Record<string, unknown>;
  }>;
  rows_returned: number;
  duration_ms: number;
}