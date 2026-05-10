import { Line, LineChart, ResponsiveContainer, YAxis } from 'recharts';

interface Props {
  data: number[];
  color: string;
  height?: number;
  yMin?: number;
  yMax?: number;
}

export function Sparkline({ data, color, height = 32, yMin, yMax }: Props) {
  const chartData = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 2, bottom: 2, left: 0, right: 0 }}>
        <YAxis hide domain={[yMin ?? 'dataMin', yMax ?? 'dataMax']} />
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}