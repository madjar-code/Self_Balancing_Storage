import { tokens } from '../theme/tokens';

/** Map temperature [0..1+] to an orange→red gradient over the cold base. */
export function temperatureToColor(t: number): string {
  if (!isFinite(t) || t <= 0) return tokens.accent.cold;
  const clamped = Math.min(1, t);
  /** Interpolate hue 25 (orange) to 0 (red) by clamped temp. */
  const hue = 25 - 25 * clamped;
  const lightness = 35 + 15 * clamped;
  return `hsl(${hue}, 90%, ${lightness}%)`;
}

export function pressureColor(p: number): string {
  if (p < 0.7) return tokens.pressure.ok;
  if (p < 0.9) return tokens.pressure.mid;
  return tokens.pressure.bad;
}