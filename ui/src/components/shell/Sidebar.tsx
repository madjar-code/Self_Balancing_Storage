import styled from 'styled-components';
import { NavLink } from 'react-router-dom';
import { useEngineState } from '../../api/hooks';
import { useDecisions } from '../../context/DecisionsContext';
import { pressureColor } from '../../lib/color';

const Aside = styled.aside`
  width: 220px;
  flex-shrink: 0;
  background: ${({ theme }) => theme.bg.panel};
  border-right: 1px solid ${({ theme }) => theme.border};
  display: flex;
  flex-direction: column;
  padding: ${({ theme }) => theme.spacing.lg}px ${({ theme }) => theme.spacing.md}px;
  gap: ${({ theme }) => theme.spacing.xs}px;
`;

const Brand = styled.div`
  font-family: ${({ theme }) => theme.font.mono};
  font-size: 13px;
  color: ${({ theme }) => theme.text.muted};
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin-bottom: ${({ theme }) => theme.spacing.lg}px;
`;

const Item = styled(NavLink)`
  padding: ${({ theme }) => theme.spacing.sm}px ${({ theme }) => theme.spacing.md}px;
  border-radius: ${({ theme }) => theme.radius.sm}px;
  color: ${({ theme }) => theme.text.muted};
  font-weight: 500;
  &.active {
    background: ${({ theme }) => theme.bg.elev};
    color: ${({ theme }) => theme.text.fg};
  }
  &:hover { background: ${({ theme }) => theme.bg.elev}; }
`;

const Footer = styled.div`
  margin-top: auto;
  padding-top: ${({ theme }) => theme.spacing.lg}px;
  border-top: 1px solid ${({ theme }) => theme.border};
  font-size: 12px;
  color: ${({ theme }) => theme.text.muted};
  display: flex;
  flex-direction: column;
  gap: 6px;
`;

const Dot = styled.span<{ $color: string }>`
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${({ $color }) => $color};
  margin-right: 6px;
`;

const PressureBar = styled.div`
  height: 6px;
  background: ${({ theme }) => theme.bg.elev};
  border-radius: 3px;
  overflow: hidden;
`;

const PressureFill = styled.div<{ $pct: number; $color: string }>`
  height: 100%;
  width: ${({ $pct }) => $pct}%;
  background: ${({ $color }) => $color};
  transition: width 200ms ease;
`;

export function Sidebar() {
  const { data: state } = useEngineState();
  const { connected } = useDecisions();
  const pressure = state?.memory_pressure ?? 0;

  return (
    <Aside>
      <Brand>SBS Dashboard</Brand>
      <Item to="/" end>Overview</Item>
      <Item to="/chunks">Chunks</Item>
      <Item to="/indexes">Indexes</Item>
      <Item to="/decisions">Decisions</Item>
      <Item to="/query">Query</Item>
      <Footer>
        <div>
          <Dot $color={connected ? '#22c55e' : '#ef4444'} />
          {connected ? 'Live' : 'Disconnected'}
        </div>
        <div>
          Burst: {state?.is_burst ? <strong style={{ color: '#f59e0b' }}>active</strong> : 'idle'}
        </div>
        <div>Memory pressure: {(pressure * 100).toFixed(0)}%</div>
        <PressureBar>
          <PressureFill $pct={Math.min(100, pressure * 100)} $color={pressureColor(pressure)} />
        </PressureBar>
      </Footer>
    </Aside>
  );
}
