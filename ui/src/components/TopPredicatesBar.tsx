import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from 'recharts';
import { TopPredicate } from '../api/types';
import { tokens } from '../theme/tokens';

interface Props {
  predicates: TopPredicate[];
  height?: number;
}

export function TopPredicatesBar({ predicates, height = 260 }: Props) {
  const data = predicates.slice(0, 10).map((p) => ({
    name: `${p.field}=${truncate(String(p.value), 20)}`,
    freq: p.freq,
  }));
  if (data.length === 0) {
    return <div style={{ color: tokens.text.muted, padding: 16, fontStyle: 'italic' }}>No predicates yet.</div>;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 80, right: 16, top: 8, bottom: 8 }}>
        <XAxis type="number" stroke={tokens.text.muted} fontSize={11} />
        <YAxis type="category" dataKey="name" stroke={tokens.text.muted} fontSize={11} width={140} />
        <Tooltip
          contentStyle={{ background: tokens.bg.elev, border: `1px solid ${tokens.border}` }}
          labelStyle={{ color: tokens.text.fg }}
          itemStyle={{ color: tokens.text.fg }}
        />
        <Bar dataKey="freq" fill={tokens.index.hash} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}