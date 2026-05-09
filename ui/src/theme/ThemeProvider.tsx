import { ThemeProvider as SCProvider } from 'styled-components';
import { ReactNode } from 'react';
import { tokens } from './tokens';

export function ThemeProvider({ children }: { children: ReactNode }) {
  return <SCProvider theme={tokens}>{children}</SCProvider>;
}