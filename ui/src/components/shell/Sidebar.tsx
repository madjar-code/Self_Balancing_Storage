import styled from "styled-components";
import { NavLink } from "react-router-dom";



const Aside = styled.aside`
  width: 220px;
  flex-shrink: 0;
  background: ${({ theme }) => theme.bg.panel};
  border-right: 1px solid ${({ theme }) => theme.border};
  display: flex;
  flex-direction: column;
  padding: ${({ theme }) => theme.spacing.lg}px ${({ theme }) => theme.spacing.md}px;
  gap: ${({ theme }) => theme.spacing.xs}px;
`;

const Brand = styled.div`
  font-family: ${({ theme }) => theme.font.mono};
  font-size: 13px;
  color: ${({ theme }) => theme.text.muted};
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin-bottom: ${({ theme }) => theme.spacing.lg}px;
`;

const Item = styled(NavLink)`
  padding: ${({ theme }) => theme.spacing.sm}px ${({ theme }) => theme.spacing.md}px;
  border-radius: ${({ theme }) => theme.radius.sm}px;
  color: ${({ theme }) => theme.text.muted};
  font-weight: 500;
  &.active {
    background: ${({ theme }) => theme.bg.elev};
    color: ${({ theme }) => theme.text.fg};
  }
  &:hover { background: ${({ theme }) => theme.bg.elev}; }
`;

const Footer = styled.div`
  margin-top: auto;
  padding-top: ${({ theme }) => theme.spacing.lg}px;
  border-top: 1px solid ${({ theme }) => theme.border};
  font-size: 12px;
  color: ${({ theme }) => theme.text.muted};
`;

export function Sidebar() {
  return (
    <Aside>
      <Brand>SBS Dashboard</Brand>
      <Item to="/" end>Overview</Item>
      <Item to="/chunks">Chunks</Item>
      <Item to="/indexes">Indexes</Item>
      <Item to="/decisions">Decisions</Item>
      <Item to="/query">Query</Item>
      <Footer>● Live  •  Burst: —  •  Mem: —</Footer>
    </Aside>
  );
}