import styled from 'styled-components';
import { DecisionEvent } from '../api/types';
import { DecisionItem } from './DecisionItem';

const Wrap = styled.div<{ $maxHeight: string }>`
  background: ${({ theme }) => theme.bg.panel};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.md}px;
  overflow-y: auto;
  max-height: ${({ $maxHeight }) => $maxHeight};
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
  /** CSS max-height for the scrollable feed. Defaults to 480px. */
  maxHeight?: string;
}

export function DecisionsFeed({ decisions, maxItems = 200, maxHeight = '480px' }: Props) {
  const items = decisions.slice(0, maxItems);
  if (items.length === 0) {
    return <Wrap $maxHeight={maxHeight}><Empty>Waiting for engine decisions…</Empty></Wrap>;
  }
  return (
    <Wrap $maxHeight={maxHeight}>
      {items.map((e, i) => <DecisionItem key={`${e.ts}-${i}`} event={e} />)}
    </Wrap>
  );
}