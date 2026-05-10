import styled from 'styled-components';
import { useState } from 'react';
import { useDecisions } from '../context/DecisionsContext';
import { DecisionsFeed } from '../components/DecisionsFeed';

const Bar = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.sm}px;
  flex-wrap: wrap;
  margin-bottom: ${({ theme }) => theme.spacing.md}px;
`;

const Chip = styled.button<{ $active: boolean }>`
  background: ${({ $active, theme }) => ($active ? theme.bg.elev : theme.bg.panel)};
  color: ${({ theme }) => theme.text.fg};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: 20px;
  padding: 4px 10px;
  font-size: 12px;
`;

const FILTERS = [
  { key: 'all', label: 'all' },
  { key: 'build_index', label: 'build' },
  { key: 'drop_index', label: 'drop' },
  { key: 'restore_index', label: 'restore' },
  { key: 'promote', label: 'promote' },
  { key: 'demote', label: 'demote' },
  { key: 'evict_heavy_index', label: 'evict' },
  { key: 'burst', label: 'burst' },
  { key: 'tier_change', label: 'tier' },
] as const;

type FilterKey = typeof FILTERS[number]['key'];

export default function DecisionsPage() {
  const { decisions } = useDecisions();
  const [active, setActive] = useState<FilterKey>('all');

  const visible = active === 'all'
    ? decisions
    : decisions.filter(d => d.action === active || d.type === active);

  return (
    <div>
      <Bar>
        {FILTERS.map(f => (
          <Chip key={f.key} $active={active === f.key} onClick={() => setActive(f.key)}>
            {f.label}
          </Chip>
        ))}
        <span style={{ marginLeft: 'auto', alignSelf: 'center', color: 'inherit', opacity: 0.7 }}>
          {visible.length} of {decisions.length}
        </span>
      </Bar>
      <DecisionsFeed decisions={visible} maxItems={500} />
    </div>
  );
}