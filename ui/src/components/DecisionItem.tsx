import styled from 'styled-components';
import { DecisionEvent } from '../api/types';
import { formatRelative } from '../lib/format';

const Row = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.sm}px;
  padding: ${({ theme }) => theme.spacing.xs}px ${({ theme }) => theme.spacing.sm}px;
  border-bottom: 1px solid ${({ theme }) => theme.border};
  font-size: 12px;
  font-family: ${({ theme }) => theme.font.mono};
`;

const Glyph = styled.span<{ $color: string }>`
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: ${({ $color }) => $color};
  flex-shrink: 0;
`;

const Time = styled.span`
  color: ${({ theme }) => theme.text.dim};
  margin-left: auto;
  flex-shrink: 0;
`;

const Detail = styled.span`
  color: ${({ theme }) => theme.text.fg};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const PALETTE: Record<string, string> = {
  build_index: '#22c55e',
  drop_index: '#ef4444',
  restore_index: '#a78bfa',
  promote: '#f59e0b',
  demote: '#60a5fa',
  evict_heavy_index: '#fb7185',
  burst: '#f59e0b',
  tier_change: '#60a5fa',
};

export function DecisionItem({ event }: { event: DecisionEvent }) {
  const key = event.action ?? event.type;
  const color = PALETTE[key] ?? '#6b7280';
  const detail = describe(event);
  return (
    <Row>
      <Glyph $color={color} title={key} />
      <Detail title={detail}>{detail}</Detail>
      <Time>{formatRelative(event.ts)}</Time>
    </Row>
  );
}

function describe(e: DecisionEvent): string {
  if (e.type === 'burst') return `burst ${e.state} (ratio ${e.ratio?.toFixed(2)})`;
  if (e.type === 'tier_change') return `${e.chunk_id} ${e.from} → ${e.to}`;
  if (e.action === 'build_index' || e.action === 'restore_index') {
    return `${e.action} ${e.index_type} on ${e.chunk_id} ${e.predicate?.field}`;
  }
  if (e.action === 'drop_index' || e.action === 'evict_heavy_index') {
    return `${e.action} ${e.index_id ?? ''}`;
  }
  if (e.action === 'promote' || e.action === 'demote') {
    return `${e.action} ${e.chunk_id}`;
  }
  return JSON.stringify(e);
}