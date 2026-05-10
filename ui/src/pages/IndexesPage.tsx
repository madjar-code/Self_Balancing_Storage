import styled from 'styled-components';
import { useIndexes, useTopPredicates } from '../api/hooks';
import { IndexTable } from '../components/IndexTable';
import { TopPredicatesBar } from '../components/TopPredicatesBar';
import { formatBytes } from '../lib/format';

const Row = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: ${({ theme }) => theme.spacing.md}px;
  margin-bottom: ${({ theme }) => theme.spacing.lg}px;
`;

const Stat = styled.div`
  background: ${({ theme }) => theme.bg.panel};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.md}px;
  padding: ${({ theme }) => theme.spacing.md}px;
`;

const StatTitle = styled.div`
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: ${({ theme }) => theme.text.muted};
`;

const StatValue = styled.div`
  font-family: ${({ theme }) => theme.font.mono};
  font-size: 18px;
  font-weight: 600;
`;

const SectionTitle = styled.h3`
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: ${({ theme }) => theme.text.muted};
  margin: ${({ theme }) => theme.spacing.lg}px 0 ${({ theme }) => theme.spacing.sm}px 0;
`;

const Panel = styled.div`
  background: ${({ theme }) => theme.bg.panel};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.md}px;
  padding: ${({ theme }) => theme.spacing.md}px;
`;

export default function IndexesPage() {
  const { data: indexes = [] } = useIndexes();
  const { data: predicates = [] } = useTopPredicates();

  const active = indexes.filter(i => i.status === 'active');
  const dropped = indexes.filter(i => i.status === 'dropped');
  const totalMem = active.reduce((s, i) => s + i.memory_bytes, 0);
  const byType: Record<string, number> = {};
  for (const i of active) byType[i.type] = (byType[i.type] ?? 0) + 1;

  return (
    <div>
      <Row>
        <Stat><StatTitle>Active indexes</StatTitle><StatValue>{active.length}</StatValue></Stat>
        <Stat><StatTitle>Dropped (waiting)</StatTitle><StatValue>{dropped.length}</StatValue></Stat>
        <Stat><StatTitle>Total memory</StatTitle><StatValue>{formatBytes(totalMem)}</StatValue></Stat>
        <Stat>
          <StatTitle>By type</StatTitle>
          <StatValue>
            {Object.entries(byType).map(([t, n]) => `${t}:${n}`).join('  ') || '—'}
          </StatValue>
        </Stat>
      </Row>

      <SectionTitle>Top predicates</SectionTitle>
      <Panel><TopPredicatesBar predicates={predicates} /></Panel>

      <SectionTitle>All indexes</SectionTitle>
      <Panel><IndexTable indexes={indexes} /></Panel>
    </div>
  );
}