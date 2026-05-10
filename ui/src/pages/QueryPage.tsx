import styled from 'styled-components';
import { useState } from 'react';
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

export default function QueryPage() {
  const [q, setQ] = useState('service="auth-api"');
  const mut = useRunQuery();

  function run() { if (q.trim()) mut.mutate(q.trim()); }

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
          <Meta>{mut.data.rows_returned} rows · {formatMs(mut.data.duration_ms)}</Meta>
          <Panel>
            <pre style={{ margin: 0 }}>{JSON.stringify(mut.data.results, null, 2)}</pre>
          </Panel>
        </>
      )}
    </div>
  );
}