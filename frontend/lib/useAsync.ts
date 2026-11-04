"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Minimal data-fetching hook: runs `fn` whenever `deps` change and exposes data/error/loading.
 * `reload(true)` refetches silently (keeps current data on screen), which is what polling wants.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  const callId = useRef(0);

  useEffect(() => {
    fnRef.current = fn;
  });

  const reload = useCallback(async (silent = false) => {
    const id = ++callId.current;
    if (!silent) setLoading(true);
    try {
      const result = await fnRef.current();
      if (id === callId.current) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (id === callId.current) setError(e);
    } finally {
      if (id === callId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, reload, setData };
}
