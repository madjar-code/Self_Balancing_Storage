import styled from 'styled-components';
import { useMemo, useState } from 'react';
import { IndexInfo } from '../api/types';
import { IndexTypeBadge } from './badges/IndexTypeBadge';
import { formatBytes, formatRelative } from '../lib/format';

type SortKey = 'chunk_id' | 'type' | 'field' | 'memory_bytes' | 'usage' | 'last_used' | 'status';

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
`;

const Th = styled.th<{ $sortable?: boolean }>`
  text-align: left;
  padding: ${({ theme }) => theme.spacing.sm}px ${({ theme }) => theme.spacing.md}px;
  font-weight: 600;
  color: ${({ theme }) => theme.text.muted};
  border-bottom: 1px solid ${({ theme }) => theme.border};
  cursor: ${({ $sortable }) => ($sortable ? 'pointer' : 'default')};
  user-select: none;
`;

const Td = styled.td`
  padding: ${({ theme }) => theme.spacing.sm}px ${({ theme }) => theme.spacing.md}px;
  border-bottom: 1px solid ${({ theme }) => theme.border};
  font-family: ${({ theme }) => theme.font.mono};
`;

const Status = styled.span<{ $status: string }>`
  color: ${({ $status, theme }) => ($status === 'active' ? theme.pressure.ok : theme.text.muted)};
`;

function compare(a: IndexInfo, b: IndexInfo, key: SortKey, dir: 1 | -1): number {
  const av = a[key];
  const bv = b[key];
  if (av == null && bv == null) return 0;
  if (av == null) return 1;
  if (bv == null) return -1;
  if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
  return String(av).localeCompare(String(bv)) * dir;
}

export function IndexTable({ indexes }: { indexes: IndexInfo[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('memory_bytes');
  const [sortDir, setSortDir] = useState<1 | -1>(-1);

  const sorted = useMemo(() => {
    const copy = [...indexes];
    copy.sort((a, b) => compare(a, b, sortKey, sortDir));
    return copy;
  }, [indexes, sortKey, sortDir]);

  function clickHeader(key: SortKey) {
    if (key === sortKey) setSortDir(sortDir === 1 ? -1 : 1);
    else { setSortKey(key); setSortDir(-1); }
  }

  const cols: Array<{ key: SortKey; label: string }> = [
    { key: 'chunk_id', label: 'Chunk' },
    { key: 'type', label: 'Type' },
    { key: 'field', label: 'Field' },
    { key: 'memory_bytes', label: 'Memory' },
    { key: 'usage', label: 'Usage' },
    { key: 'last_used', label: 'Last used' },
    { key: 'status', label: 'Status' },
  ];

  return (
    <Table>
      <thead>
        <tr>
          {cols.map(c => (
            <Th key={c.key} $sortable onClick={() => clickHeader(c.key)}>
              {c.label}{sortKey === c.key ? (sortDir === 1 ? ' ▲' : ' ▼') : ''}
            </Th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map(i => (
          <tr key={i.index_id}>
            <Td>{i.chunk_id}</Td>
            <Td><IndexTypeBadge type={i.type} /></Td>
            <Td>{i.field}</Td>
            <Td>{formatBytes(i.memory_bytes)}</Td>
            <Td>{i.usage}</Td>
            <Td>{i.last_used ? formatRelative(i.last_used) : '—'}</Td>
            <Td><Status $status={i.status}>{i.status}</Status></Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}