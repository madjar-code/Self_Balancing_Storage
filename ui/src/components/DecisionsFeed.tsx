import styled, { css } from 'styled-components';
import { DecisionEvent } from '../api/types';
import { DecisionItem } from './DecisionItem';

const Wrap = styled.div<{ $maxHeight: string; $fill: boolean }>`
  background: ${({ theme }) => theme.bg.panel};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.md}px;
  overflow-y: auto;
  ${({ $fill, $maxHeight }) => $fill
    ? css`flex: 1; min-height: 0;`
    : css`max-height: ${$maxHeight};`}
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
  /** CSS max-height for the scrollable feed. Defaults to 480px. Ignored when fill=true. */
  maxHeight?: string;
  /** Stretch to fill the available height of the parent flex container. */
  fill?: boolean;
}

export function DecisionsFeed({
  decisions,
  maxItems = 200,
  maxHeight = '480px',
  fill = false,
}: Props) {
  const items = decisions.slice(0, maxItems);
  if (items.length === 0) {
    return (
      <Wrap $maxHeight={maxHeight} $fill={fill}>
        <Empty>Waiting for engine decisions…</Empty>
      </Wrap>
    );
  }
  return (
    <Wrap $maxHeight={maxHeight} $fill={fill}>
      {items.map((e, i) => <DecisionItem key={`${e.ts}-${i}`} event={e} />)}
    </Wrap>
  );
}