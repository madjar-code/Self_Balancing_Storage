import styled from 'styled-components';
import { ChunkInfo } from '../api/types';
import { ChunkCell } from './ChunkCell';

interface Props {
  chunks: ChunkInfo[];
  /** Fixed cell size in px. Grid wraps to fit available width. */
  cellSize?: number;
}

const Grid = styled.div<{ $cell: number }>`
  display: grid;
  grid-template-columns: repeat(auto-fill, ${({ $cell }) => $cell}px);
  gap: ${({ theme }) => theme.spacing.xs}px;
  justify-content: start;
`;

const Empty = styled.div`
  color: ${({ theme }) => theme.text.muted};
  font-style: italic;
  padding: ${({ theme }) => theme.spacing.lg}px;
  text-align: center;
`;

export function HeatmapGrid({ chunks, cellSize = 100 }: Props) {
  if (chunks.length === 0) return <Empty>No chunks yet. Ingest some logs to see the heatmap.</Empty>;
  return (
    <Grid $cell={cellSize}>
      {chunks.map((c) => <ChunkCell key={c.chunk_id} chunk={c} />)}
    </Grid>
  );
}