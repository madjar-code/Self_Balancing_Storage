import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from 'recharts';
import { TopPredicate } from '../api/types';
import { tokens } from '../theme/tokens';

interface Props {
  predicates: TopPredicate[];
}

const BAR_HEIGHT = 24;
const CHART_PADDING = 32;
const MAX_BARS = 10;

export function TopPredicatesBar({ predicates }: Props) {
  const data = predicates.slice(0, MAX_BARS).map((p) => ({
    name: `${p.field}=${truncate(String(p.value), 20)}`,
    freq: p.freq,
  }));
  if (data.length === 0) {
    return <div style={{ color: tokens.text.muted, padding: 16, fontStyle: 'italic' }}>No predicates yet.</div>;
  }
  const height = data.length * BAR_HEIGHT + CHART_PADDING;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 80, right: 16, top: 8, bottom: 8 }}>
        <XAxis type="number" stroke={tokens.text.muted} fontSize={11} />
        <YAxis type="category" dataKey="name" stroke={tokens.text.muted} fontSize={11} width={140} />
        <Tooltip
          cursor={{ fill: 'rgba(255,255,255,0.04)' }}
          contentStyle={{
            background: tokens.bg.elev,
            border: `1px solid ${tokens.border}`,
            borderRadius: tokens.radius.sm,
            padding: '4px 8px',
          }}
          labelStyle={{ color: tokens.text.fg, fontSize: 12 }}
          itemStyle={{ color: tokens.text.fg, fontSize: 12 }}
          separator=" — "
          formatter={(v: number) => [v, 'freq']}
        />
        <Bar dataKey="freq" fill={tokens.index.hash} barSize={BAR_HEIGHT - 8} radius={[0, 2, 2, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}