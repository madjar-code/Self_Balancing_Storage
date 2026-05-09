import 'styled-components';
import { Theme } from './tokens';

declare module 'styled-components' {
  export interface DefaultTheme extends Theme {}
}