import { ThemeProvider } from './theme/ThemeProvider';
import { GlobalStyle } from './theme/globals';

export default function App() {
  return (
    <ThemeProvider>
      <GlobalStyle />
      <div style={{ padding: 32 }}>SBS UI - theme wired</div>
    </ThemeProvider>
  );
}