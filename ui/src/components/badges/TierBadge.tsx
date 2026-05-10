import styled from 'styled-components';

const BadgeBase = styled.span<{ $bg: string; $fg: string }>`
  display: inline-block;
  padding: 1px 6px;
  border-radius: ${({ theme }) => theme.radius.sm}px;
  font-family: ${({ theme }) => theme.font.mono};
  font-size: 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  background: ${({ $bg }) => $bg};
  color: ${({ $fg }) => $fg};
`;

export function TierBadge({ tier }: { tier: 'hot' | 'cold' }) {
  const bg = tier === 'hot' ? '#9a3412' : '#1f2a44';
  const fg = '#ffe7d6';
  return <BadgeBase $bg={bg} $fg={fg}>{tier}</BadgeBase>;
}