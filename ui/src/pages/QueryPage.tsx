import styled from 'styled-components';
import { useEffect, useMemo, useState } from 'react';
import { useRunQuery } from '../api/hooks';
import { formatMs } from '../lib/format';

const Row = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.sm}px;
  margin-bottom: ${({ theme }) => theme.spacing.md}px;
`;

const Input = styled.input`
  flex: 1;
  background: ${({ theme }) => theme.bg.panel};
  color: ${({ theme }) => theme.text.fg};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.sm}px;
  padding: ${({ theme }) => theme.spacing.sm}px ${({ theme }) => theme.spacing.md}px;
  font-family: ${({ theme }) => theme.font.mono};
  font-size: 13px;
`;

const Button = styled.button`
  background: ${({ theme }) => theme.bg.elev};
  color: ${({ theme }) => theme.text.fg};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.sm}px;
  padding: ${({ theme }) => theme.spacing.sm}px ${({ theme }) => theme.spacing.md}px;

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

const Panel = styled.div`
  background: ${({ theme }) => theme.bg.panel};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.md}px;
  padding: ${({ theme }) => theme.spacing.md}px;
  font-family: ${({ theme }) => theme.font.mono};
  font-size: 12px;
  max-height: 600px;
  overflow: auto;
`;

const Meta = styled.div`
  font-size: 12px;
  color: ${({ theme }) => theme.text.muted};
  margin-bottom: ${({ theme }) => theme.spacing.sm}px;
`;

const Pager = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.sm}px;
  margin: ${({ theme }) => theme.spacing.sm}px 0;
  font-size: 12px;
  color: ${({ theme }) => theme.text.muted};
  font-feature-settings: 'tnum' 1;
`;

const PageButton = styled(Button)`
  padding: 2px 10px;
  font-size: 12px;
`;

const PageSizeSelect = styled.select`
  background: ${({ theme }) => theme.bg.panel};
  color: ${({ theme }) => theme.text.fg};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.sm}px;
  padding: 2px 6px;
  font: inherit;
`;

const Error = styled.pre`
  color: ${({ theme }) => theme.pressure.bad};
  background: ${({ theme }) => theme.bg.panel};
  padding: ${({ theme }) => theme.spacing.md}px;
  border-radius: ${({ theme }) => theme.radius.md}px;
  white-space: pre-wrap;
  margin: 0;
`;

const EXAMPLES = [
  'service="auth-api"',
  'level="ERROR"',
  'service="billing" and level="WARN"',
];

const PAGE_SIZE_OPTIONS = [25, 50, 100, 250, 500];

export default function QueryPage() {
  const [q, setQ] = useState('service="auth-api"');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const mut = useRunQuery();

  function run() {
    if (q.trim()) mut.mutate(q.trim());
  }

  /** Reset page when a new result lands. */
  useEffect(() => {
    if (mut.data) setPage(1);
  }, [mut.data]);

  const total = mut.data?.results.length ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);
  const visible = useMemo(() => {
    if (!mut.data) return [];
    const start = (safePage - 1) * pageSize;
    return mut.data.results.slice(start, start + pageSize);
  }, [mut.data, safePage, pageSize]);

  return (
    <div>
      <Row>
        <Input
          value={q}
          onChange={e => setQ(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()}
          placeholder='service="auth-api"'
        />
        <Button onClick={run} disabled={mut.isPending}>
          {mut.isPending ? 'Running…' : 'Execute'}
        </Button>
      </Row>

      <Meta>
        Examples: {EXAMPLES.map((ex, i) => (
          <span key={ex}>
            {i > 0 && ' · '}
            <a href="#" onClick={e => { e.preventDefault(); setQ(ex); }}>{ex}</a>
          </span>
        ))}
      </Meta>

      {mut.isError && <Error>{String(mut.error)}</Error>}
      {mut.data && (
        <>
          <Meta>
            {total.toLocaleString()} rows · {formatMs(mut.data.duration_ms)}
          </Meta>

          <Pager>
            <span>
              Showing {((safePage - 1) * pageSize + 1).toLocaleString()}–
              {Math.min(safePage * pageSize, total).toLocaleString()} of {total.toLocaleString()}
            </span>
            <span style={{ marginLeft: 'auto' }}>Page size:</span>
            <PageSizeSelect
              value={pageSize}
              onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
            >
              {PAGE_SIZE_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
            </PageSizeSelect>
            <PageButton onClick={() => setPage(1)} disabled={safePage <= 1}>
              ⏮
            </PageButton>
            <PageButton onClick={() => setPage(p => Math.max(1, p - 1))} disabled={safePage <= 1}>
              ←
            </PageButton>
            <span>Page {safePage} of {totalPages}</span>
            <PageButton
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={safePage >= totalPages}
            >
              →
            </PageButton>
            <PageButton onClick={() => setPage(totalPages)} disabled={safePage >= totalPages}>
              ⏭
            </PageButton>
          </Pager>

          <Panel>
            <pre style={{ margin: 0 }}>{JSON.stringify(visible, null, 2)}</pre>
          </Panel>
        </>
      )}
    </div>
  );
}
