import { useEngineState } from '../api/hooks';

export default function OverviewPage() {
  const { data, isLoading, error } = useEngineState();
  if (isLoading) return <p>loading…</p>;
  if (error) return <p>error: {String(error)}</p>;
  return <pre>{JSON.stringify(data, null, 2)}</pre>;
}