import styled from 'styled-components';
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

const Tooltip = styled.div`
  position: absolute;
  top: 110%;
  left: 0;
  pointer-events: none;
  background: ${({ theme }) => theme.bg.elev};
  border: 1px solid ${({ theme }) => theme.border};
  border-radius: ${({ theme }) => theme.radius.sm}px;
  padding: ${({ theme }) => theme.spacing.sm}px;
  font-family: ${({ theme }) => theme.font.mono};
  font-size: 11px;
  white-space: nowrap;
  z-index: 10;
  display: none;
  ${Cell}:hover & { display: block; }
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

export function ChunkCell({ chunk }: { chunk: ChunkInfo }) {
  const bg = temperatureToColor(chunk.temperature);
  const border = tierBorder[chunk.tier] ?? tokens.border;
  return (
    <Cell $bg={bg} $border={border}>
      {chunk.indexes.length > 0 && (
        <Dots>
          {chunk.indexes.slice(0, 8).map((iid) => (
            <Dot key={iid} $bg={indexDotColor(iid)} />
          ))}
        </Dots>
      )}
      <Tooltip>
        <div>{chunk.chunk_id}</div>
        <div>tier: {chunk.tier} • state: {chunk.state}</div>
        <div>count: {chunk.count.toLocaleString()}</div>
        <div>temp: {chunk.temperature.toFixed(2)}</div>
        <div>indexes: {chunk.indexes.length}</div>
      </Tooltip>
    </Cell>
  );
}