import styled from 'styled-components';
import { useState } from 'react';
import { useChunks } from '../api/hooks';
import { HeatmapGrid } from '../components/HeatmapGrid';
import { TierBadge } from '../components/badges/TierBadge';
import { StateBadge } from '../components/badges/StateBadge';
import { formatRelative } from '../lib/format';

import { sortChunksOpenFirst } from '../lib/sortChunks';

type Tier = 'all' | 'hot' | 'cold';
type State = 'all' | 'open' | 'sealed' | 'persisted';
type View = 'grid' | 'table';

const Bar = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.md}px;
  margin-bottom: ${({ theme }) => theme.spacing.md}px;
  align-items: center;
`;

const Select = styled.select`
  background: ${({ theme }) => theme.bg.panel};
  color: ${({ theme }) => theme.text.fg};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.sm}px;
  padding: 4px 8px;
  font: inherit;
`;

const Toggle = styled.button<{ $active: boolean }>`
  background: ${({ $active, theme }) => ($active ? theme.bg.elev : theme.bg.panel)};
  color: ${({ theme }) => theme.text.fg};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.sm}px;
  padding: 4px 8px;
`;

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  font-family: ${({ theme }) => theme.font.sans};
  font-feature-settings: 'tnum' 1;
`;

const Th = styled.th`
  text-align: left;
  padding: ${({ theme }) => theme.spacing.sm}px ${({ theme }) => theme.spacing.md}px;
  color: ${({ theme }) => theme.text.muted};
  border-bottom: 1px solid ${({ theme }) => theme.border};
`;

const Td = styled.td`
  padding: ${({ theme }) => theme.spacing.sm}px ${({ theme }) => theme.spacing.md}px;
  border-bottom: 1px solid ${({ theme }) => theme.border};
`;

export default function ChunksPage() {
  const { data = [] } = useChunks();
  const [tier, setTier] = useState<Tier>('all');
  const [state, setState] = useState<State>('all');
  const [view, setView] = useState<View>('grid');

  const filtered = sortChunksOpenFirst(
    data.filter(c =>
      (tier === 'all' || c.tier === tier) &&
      (state === 'all' || c.state === state),
    ),
  );

  return (
    <div>
      <Bar>
        <span>Tier:</span>
        <Select value={tier} onChange={e => setTier(e.target.value as Tier)}>
          <option value="all">all</option>
          <option value="hot">hot</option>
          <option value="cold">cold</option>
        </Select>
        <span>State:</span>
        <Select value={state} onChange={e => setState(e.target.value as State)}>
          <option value="all">all</option>
          <option value="open">open</option>
          <option value="sealed">sealed</option>
          <option value="persisted">persisted</option>
        </Select>
        <span style={{ marginLeft: 'auto' }}>{filtered.length} of {data.length}</span>
        <Toggle $active={view === 'grid'} onClick={() => setView('grid')}>Grid</Toggle>
        <Toggle $active={view === 'table'} onClick={() => setView('table')}>Table</Toggle>
      </Bar>

      {view === 'grid' && <HeatmapGrid chunks={filtered} />}

      {view === 'table' && (
        <Table>
          <thead>
            <tr>
              <Th>Chunk ID</Th><Th>Tier</Th><Th>State</Th>
              <Th>Count</Th><Th>Temp</Th><Th>Indexes</Th><Th>ts_min</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(c => (
              <tr key={c.chunk_id}>
                <Td>{c.chunk_id}</Td>
                <Td><TierBadge tier={c.tier} /></Td>
                <Td><StateBadge state={c.state} /></Td>
                <Td>{c.count.toLocaleString()}</Td>
                <Td>{c.temperature.toFixed(2)}</Td>
                <Td>{c.indexes.length}</Td>
                <Td>{formatRelative(c.ts_min)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}