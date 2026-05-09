import { createGlobalStyle } from 'styled-components';

export const GlobalStyle = createGlobalStyle`
  *, *::before, *::after { box-sizing: border-box; }
  html, body, #root { margin: 0; height: 100%; }
  body {
    background: ${({ theme }) => theme.bg.base};
    color: ${({ theme }) => theme.text.fg};
    font-family: ${({ theme }) => theme.font.sans};
    font-size: 14px;
    -webkit-font-smoothing: antialiased;
  }
  a { color: inherit; text-decoration: none; }
  button { font: inherit; cursor: pointer; }
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-thumb { background: ${({ theme }) => theme.border}; border-radius: 4px; }
`;