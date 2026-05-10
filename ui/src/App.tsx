import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from './theme/ThemeProvider';
import { GlobalStyle } from './theme/globals';
import { AppShell } from './components/shell/AppShell';
import OverviewPage from './pages/OverviewPage';
import ChunksPage from './pages/ChunksPage';
import IndexesPage from './pages/IndexesPage';
import DecisionsPage from './pages/DecisionsPage';
import QueryPage from './pages/QueryPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 0, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
    <ThemeProvider>
      <GlobalStyle />
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/chunks" element={<ChunksPage />} />
            <Route path="/indexes" element={<IndexesPage />} />
            <Route path="/decisions" element={<DecisionsPage />} />
            <Route path="/query" element={<QueryPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
    </QueryClientProvider>
  );
}