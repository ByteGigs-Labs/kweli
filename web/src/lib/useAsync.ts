import { useCallback, useEffect, useState } from "react";

interface Settled<T> {
  key: string;
  data?: T;
  error?: unknown;
}

export function useAsync<T>(
  load: () => Promise<T>,
  deps: readonly (string | number | boolean | null | undefined)[],
) {
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const key = `${JSON.stringify(deps)}:${nonce}`;

  useEffect(() => {
    let active = true;
    load().then(
      (data) => active && setSettled({ key, data }),
      (error) => active && setSettled({ key, error }),
    );
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const current = settled?.key === key ? settled : null;
  const reload = useCallback(() => setNonce((value) => value + 1), []);
  const setData = useCallback((data: T) => setSettled({ key, data }), [key]);
  return {
    data: current?.data,
    error: current?.error,
    loading: current === null,
    reload,
    setData,
  };
}
