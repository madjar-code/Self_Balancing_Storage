import styled from 'styled-components';
import { ReactNode } from 'react';
import { Sparkline } from './Sparkline';

interface Props {
  title: string;
  value: ReactNode;
  subtext?: ReactNode;
  series?: number[];
  color?: string;
  yMin?: number;
  yMax?: number;
}

const Card = styled.div`
  background: ${({ theme }) => theme.bg.panel};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.md}px;
  padding: ${({ theme }) => theme.spacing.md}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.xs}px;
  min-width: 200px;
`;

const Title = styled.div`
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: ${({ theme }) => theme.text.muted};
`;

const Value = styled.div`
  font-family: ${({ theme }) => theme.font.mono};
  font-size: 22px;
  font-weight: 600;
`;

const Subtext = styled.div`
  font-size: 11px;
  color: ${({ theme }) => theme.text.dim};
`;

export function StatCard({ title, value, subtext, series, color = '#60a5fa', yMin, yMax }: Props) {
  return (
    <Card>
      <Title>{title}</Title>
      <Value>{value}</Value>
      {series !== undefined && series.length > 1 && (
        <Sparkline data={series} color={color} yMin={yMin} yMax={yMax} />
      )}
      {subtext && <Subtext>{subtext}</Subtext>}
    </Card>
  );
}