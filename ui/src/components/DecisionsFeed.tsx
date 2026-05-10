import styled from 'styled-components';
import { DecisionEvent } from '../api/types';
import { DecisionItem } from './DecisionItem';

const Wrap = styled.div`
  background: ${({ theme }) => theme.bg.panel};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.md}px;
  overflow: hidden;
  max-height: 480px;
  overflow-y: auto;
`;

const Empty = styled.div`
  padding: ${({ theme }) => theme.spacing.lg}px;
  color: ${({ theme }) => theme.text.muted};
  font-style: italic;
  text-align: center;
`;

interface Props {
  decisions: DecisionEvent[];
  maxItems?: number;
}

export function DecisionsFeed({ decisions, maxItems = 200 }: Props) {
  const items = decisions.slice(0, maxItems);
  if (items.length === 0) return <Wrap><Empty>Waiting for engine decisions…</Empty></Wrap>;
  return (
    <Wrap>
      {items.map((e, i) => <DecisionItem key={`${e.ts}-${i}`} event={e} />)}
    </Wrap>
  );
}