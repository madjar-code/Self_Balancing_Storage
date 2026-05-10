import styled from 'styled-components';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { DecisionsProvider } from '../../context/DecisionsContext';

const Layout = styled.div`
  display: flex;
  min-height: 100vh;
`;

const Main = styled.main`
  flex: 1;
  padding: ${({ theme }) => theme.spacing.xl}px;
  overflow: auto;
`;

export function AppShell() {
  return (
    <DecisionsProvider>
      <Layout>
        <Sidebar />
        <Main>
          <Outlet />
        </Main>
      </Layout>
    </DecisionsProvider>
  );
}