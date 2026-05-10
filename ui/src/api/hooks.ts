import { useQuery } from '@tanstack/react-query';
import { apiGet } from './client';
import { ChunkInfo, EngineState, IndexInfo, TopPredicate } from './types';

export function useEngineState() {
  return useQuery({
    queryKey: ['engine-state'],
    queryFn: () => apiGet<EngineState>('/engine/state'),
    refetchInterval: 1000,
    refetchIntervalInBackground: false,
  });
}

export function useChunks() {
  return useQuery({
    queryKey: ['chunks'],
    queryFn: () => apiGet<ChunkInfo[]>('/chunks'),
    refetchInterval: 1500,
    refetchIntervalInBackground: false,
  });
}

export function useIndexes() {
  return useQuery({
    queryKey: ['indexes'],
    queryFn: () => apiGet<IndexInfo[]>('/indexes'),
    refetchInterval: 2000,
    refetchIntervalInBackground: false,
  });
}

export function useTopPredicates() {
  return useQuery({
    queryKey: ['top-predicates'],
    queryFn: () => apiGet<TopPredicate[]>('/tracker/top-predicates'),
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
  });
}