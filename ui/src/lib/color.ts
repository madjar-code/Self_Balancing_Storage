import { tokens } from '../theme/tokens';

/**
 * Map temperature [0..1+] to a heat color. Anything below COLD_THRESHOLD
 * is treated as fully cold so chunks with tiny residual EMA values (which
 * never decay to exactly 0) are not rendered as faint orange. Above the
 * threshold, lightness ramps from dark to bright as t grows.
 */
const COLD_THRESHOLD = 0.05;

export function temperatureToColor(t: number): string {
  if (!isFinite(t) || t < COLD_THRESHOLD) return tokens.accent.cold;
  const clamped = Math.min(1, t);
  const hue = 25 - 25 * clamped;
  const lightness = 14 + 36 * clamped;
  return `hsl(${hue}, 80%, ${lightness}%)`;
}

export function pressureColor(p: number): string {
  if (p < 0.7) return tokens.pressure.ok;
  if (p < 0.9) return tokens.pressure.mid;
  return tokens.pressure.bad;
}