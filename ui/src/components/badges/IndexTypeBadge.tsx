import styled from 'styled-components';
import { tokens } from '../../theme/tokens';

const BadgeBase = styled.span<{ $bg: string }>`
  display: inline-block;
  padding: 1px 6px;
  border-radius: ${({ theme }) => theme.radius.sm}px;
  font-family: ${({ theme }) => theme.font.sans};
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  background: ${({ $bg }) => $bg};
  color: white;
`;

export function IndexTypeBadge({ type }: { type: 'hash' | 'skip' | 'bloom' | 'unknown' }) {
  const palette = tokens.index;
  const bg =
    type === 'hash' ? palette.hash :
    type === 'skip' ? palette.skip :
    type === 'bloom' ? palette.bloom : '#6b7280';
  return <BadgeBase $bg={bg}>{type}</BadgeBase>;
}