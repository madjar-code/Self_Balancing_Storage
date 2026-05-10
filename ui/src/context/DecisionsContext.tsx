import { createContext, ReactNode, useContext } from 'react';
import { DecisionEvent } from '../api/types';
import { useDecisionsFeed } from '../lib/useDecisionsFeed';

interface DecisionsValue {
  decisions: DecisionEvent[];
  connected: boolean;
}

const DecisionsCtx = createContext<DecisionsValue>({ decisions: [], connected: false });

export function DecisionsProvider({ children }: { children: ReactNode }) {
  const value = useDecisionsFeed();
  return <DecisionsCtx.Provider value={value}>{children}</DecisionsCtx.Provider>;
}

export function useDecisions() {
  return useContext(DecisionsCtx);
}