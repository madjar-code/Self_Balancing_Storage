import styled from 'styled-components';
import { useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChunkInfo } from '../api/types';
import { temperatureToColor } from '../lib/color';
import { tokens } from '../theme/tokens';

const Cell = styled.div<{ $bg: string; $border: string }>`
  position: relative;
  aspect-ratio: 1;
  background: ${({ $bg }) => $bg};
  border: 1.5px solid ${({ $border }) => $border};
  border-radius: ${({ theme }) => theme.radius.sm}px;
  cursor: pointer;
  transition: transform 80ms ease;
  &:hover { transform: scale(1.04); z-index: 1; }
`;

const Dots = styled.div`
  position: absolute;
  top: 2px;
  left: 2px;
  right: 2px;
  display: flex;
  gap: 2px;
  flex-wrap: wrap;
`;

const Dot = styled.span<{ $bg: string }>`
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: ${({ $bg }) => $bg};
`;

const Tooltip = styled.div<{ $top: number; $left: number }>`
  position: fixed;
  top: ${({ $top }) => $top}px;
  left: ${({ $left }) => $left}px;
  pointer-events: none;
  background: ${({ theme }) => theme.bg.elev};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.sm}px;
  padding: ${({ theme }) => theme.spacing.sm}px;
  font-family: ${({ theme }) => theme.font.sans};
  font-feature-settings: 'tnum' 1;
  font-size: 12px;
  line-height: 1.4;
  width: max-content;
  max-width: 240px;
  z-index: 1000;
`;

const tierBorder: Record<string, string> = {
  hot: '#9a3412',
  cold: '#1f2a44',
};

function indexDotColor(iid: string): string {
  if (iid.includes(':hash:')) return tokens.index.hash;
  if (iid.includes(':skip:')) return tokens.index.skip;
  if (iid.includes(':bloom:')) return tokens.index.bloom;
  return '#6b7280';
}

const TOOLTIP_MAX_W = 220;
const TOOLTIP_EST_H = 100;
const GAP = 6;

export function ChunkCell({ chunk }: { chunk: ChunkInfo }) {
  const cellRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  const bg = temperatureToColor(chunk.temperature);
  const border = tierBorder[chunk.tier] ?? tokens.border;

  function handleEnter() {
    const cell = cellRef.current;
    if (!cell) return;
    const rect = cell.getBoundingClientRect();
    /* Prefer below cell; flip up if it would overflow viewport bottom. */
    const top = rect.bottom + GAP + TOOLTIP_EST_H > window.innerHeight
      ? rect.top - GAP - TOOLTIP_EST_H
      : rect.bottom + GAP;
    /* Prefer aligned to cell's left; shift left if it would overflow right edge. */
    const left = rect.left + TOOLTIP_MAX_W > window.innerWidth
      ? Math.max(GAP, window.innerWidth - TOOLTIP_MAX_W - GAP)
      : rect.left;
    setPos({ top, left });
  }

  function handleLeave() {
    setPos(null);
  }

  return (
    <Cell
      ref={cellRef}
      $bg={bg}
      $border={border}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      {chunk.indexes.length > 0 && (
        <Dots>
          {chunk.indexes.slice(0, 8).map((iid) => (
            <Dot key={iid} $bg={indexDotColor(iid)} />
          ))}
        </Dots>
      )}
      {pos && createPortal(
        <Tooltip $top={pos.top} $left={pos.left}>
          <div>{chunk.chunk_id}</div>
          <div>tier: {chunk.tier} • state: {chunk.state}</div>
          <div>count: {chunk.count.toLocaleString()}</div>
          <div>temp: {chunk.temperature.toFixed(2)}</div>
          <div>indexes: {chunk.indexes.length}</div>
        </Tooltip>,
        document.body,
      )}
    </Cell>
  );
}
