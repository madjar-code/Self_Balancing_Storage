import styled from 'styled-components';
import { Link } from 'react-router-dom';
import { useChunks, useEngineState } from '../api/hooks';
import { useDecisions } from '../context/DecisionsContext';
import { useSeries } from '../context/TimeSeriesContext';
import { useTimeSeriesSampler } from '../lib/useTimeSeries';
import { useSeriesStore } from '../context/TimeSeriesContext';
import { StatCard } from '../components/StatCard';
import { HeatmapGrid } from '../components/HeatmapGrid';
import { DecisionsFeed } from '../components/DecisionsFeed';
import { tokens } from '../theme/tokens';
import { pressureColor } from '../lib/color';

const Row = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: ${({ theme }) => theme.spacing.md}px;
  margin-bottom: ${({ theme }) => theme.spacing.lg}px;
`;

const Section = styled.section`
  margin-bottom: ${({ theme }) => theme.spacing.xl}px;
`;

const SectionTitle = styled.h3`
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: ${({ theme }) => theme.text.muted};
  margin: 0 0 ${({ theme }) => theme.spacing.sm}px 0;
`;

const Right = styled.span`
  float: right;
  font-size: 12px;
  color: ${({ theme }) => theme.text.muted};
`;

export default function OverviewPage() {
  const { data: state } = useEngineState();
  const { data: chunks = [] } = useChunks();
  const { decisions } = useDecisions();

  const store = useSeriesStore();
  useTimeSeriesSampler(store, 'write_rate', state?.write_rate);
  useTimeSeriesSampler(store, 'burst_ratio', state?.burst_ratio);
  useTimeSeriesSampler(store, 'memory_pressure', state?.memory_pressure);

  const writeSeries = useSeries('write_rate');
  const burstSeries = useSeries('burst_ratio');
  const pressureSeries = useSeries('memory_pressure');

  return (
    <div>
      <Row>
        <StatCard
          title="Write rate"
          value={state ? `${state.write_rate.toFixed(0)} /s` : '—'}
          series={writeSeries}
          color={tokens.accent.sse}
        />
        <StatCard
          title="Burst ratio"
          value={state ? state.burst_ratio.toFixed(2) : '—'}
          subtext={state?.is_burst ? 'BURST MODE' : 'steady'}
          series={burstSeries}
          color={tokens.accent.burst}
        />
        <StatCard
          title="Memory pressure"
          value={state ? `${(state.memory_pressure * 100).toFixed(1)} %` : '—'}
          series={pressureSeries}
          color={pressureColor(state?.memory_pressure ?? 0)}
          yMin={0}
          yMax={1}
        />
      </Row>

      <Section>
        <SectionTitle>
          Chunks
          <Right>{chunks.length} total • {chunks.filter(c => c.tier === 'hot').length} hot</Right>
        </SectionTitle>
        <HeatmapGrid chunks={chunks} />
      </Section>

      <Section>
        <SectionTitle>
          Recent decisions
          <Right><Link to="/decisions" style={{ color: tokens.text.muted }}>see all →</Link></Right>
        </SectionTitle>
        <DecisionsFeed decisions={decisions} maxItems={10} />
      </Section>
    </div>
  );
}