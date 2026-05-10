export const tokens = {
  bg: {
    base: '#0e1116',
    panel: '#181d24',
    elev: '#202733',
  },
  text: {
    fg: '#e8eaed',
    muted: '#8a93a3',
    dim: '#5b6374',
  },
  accent: {
    cold: '#1f2a44',
    burst: '#f59e0b',
    sse: '#22c55e',
    sseLost: '#ef4444',
  },
  pressure: {
    ok: '#22c55e',
    mid: '#f59e0b',
    bad: '#ef4444',
  },
  index: {
    hash: '#60a5fa',
    skip: '#a78bfa',
    bloom: '#fb7185',
  },
  border: '#2a313d',
  radius: { sm: 4, md: 8, lg: 12 },
  spacing: { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 },
  font: {
    mono: '"JetBrains Mono", Menlo, Consolas, monospace',
    sans: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
} as const;

export type Theme = typeof tokens;