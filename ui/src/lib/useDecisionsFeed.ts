import { useCallback, useReducer } from 'react';
import { DecisionEvent } from '../api/types';
import { useSSE } from './useSSE';

type Action = { type: 'append'; event: DecisionEvent };

function reducer(state: DecisionEvent[], action: Action): DecisionEvent[] {
  if (action.type === 'append') {
    const next = [action.event, ...state];
    return next.slice(0, 200);
  }
  return state;
}

export function useDecisionsFeed() {
  const [decisions, dispatch] = useReducer(reducer, [] as DecisionEvent[]);
  const onEvent = useCallback((raw: string) => {
    try {
      const event = JSON.parse(raw) as DecisionEvent;
      dispatch({ type: 'append', event });
    } catch {
      /* malformed line; skip */
    }
  }, []);
  const { connected } = useSSE('/api/events', onEvent);
  return { decisions, connected };
}