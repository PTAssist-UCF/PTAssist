import { useEffect, useState } from 'react';

import { useGetSession } from '@/api/sessions';

export const POLL_INTERVAL_MS = 3000;

// Must be >= the backend's cutoff for sessions stuck in "processing" (SCRUM-66),
// which is itself longer than the 230 s AI call timeout. The page must never give
// up before the backend does. 300 s is a placeholder until SCRUM-66 sets its value.
// See docs/analysis-result.md#clip-limits-and-timing
export const POLL_TIMEOUT_MS = 300_000;

export function useSessionStatus(sessionId: string | undefined) {
  // Remember which session timed out, so a new sessionId starts fresh.
  const [timedOutId, setTimedOutId] = useState<string | undefined>();
  const timedOut = sessionId !== undefined && timedOutId === sessionId;

  const query = useGetSession(sessionId ?? '', {
    query: {
      enabled: Boolean(sessionId) && !timedOut,
      // Keep polling while the tab is hidden. Otherwise polling pauses but the timeout
      // below keeps running, so a patient who switches tabs would see "timed out" even
      // after the analysis finished.
      refetchIntervalInBackground: true,
      refetchInterval: (q) => {
        if (q.state.status === 'error') return false; // e.g. 404: retrying won't help
        const status = q.state.data?.status;
        return status === 'complete' || status === 'failed' ? false : POLL_INTERVAL_MS;
      },
    },
  });

  const status = query.data?.status;
  const isDone = status === 'complete' || status === 'failed';
  const isPolling = Boolean(sessionId) && !isDone && !query.isError && !timedOut;

  useEffect(() => {
    if (!isPolling) return;
    const timer = setTimeout(() => setTimedOutId(sessionId), POLL_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [isPolling, sessionId]);

  return { session: query.data, status, isDone, timedOut, error: query.error };
}
