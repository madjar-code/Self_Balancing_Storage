import styled from 'styled-components';

const BadgeBase = styled.span<{ $bg: string; $fg: string }>`
  display: inline-block;
  padding: 1px 6px;
  border-radius: ${({ theme }) => theme.radius.sm}px;
  font-family: ${({ theme }) => theme.font.sans};
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  background: ${({ $bg }) => $bg};
  color: ${({ $fg }) => $fg};
`;

const PALETTE: Record<string, [string, string]> = {
  open: ['#1e3a8a', '#dbeafe'],
  sealed: ['#3f3f46', '#e4e4e7'],
  persisted: ['#064e3b', '#d1fae5'],
};

export function StateBadge({ state }: { state: 'open' | 'sealed' | 'persisted' }) {
  const [bg, fg] = PALETTE[state] ?? ['#374151', '#e5e7eb'];
  return <BadgeBase $bg={bg} $fg={fg}>{state}</BadgeBase>;
}