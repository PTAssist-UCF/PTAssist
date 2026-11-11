import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiFetch } from '@/apiClient';

import { POLL_INTERVAL_MS, POLL_TIMEOUT_MS, useSessionStatus } from './useSessionStatus';

vi.mock('@/apiClient', () => ({ apiFetch: vi.fn() }));
const mockApiFetch = vi.mocked(apiFetch);

const session = (status: 'processing' | 'complete' | 'failed') => ({
  id: 'session-1',
  plan_exercise_id: 'plan-exercise-1',
  status,
  created_at: '2026-11-10T12:00:00Z',
});

// setup() uses the id 'session-1'. setup({}) passes no id at all.
function setup({ id }: { id?: string } = { id: 'session-1' }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useSessionStatus(id), { wrapper });
}

const advance = (ms: number) =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
    for (let i = 0; i < 5; i++) {
      await vi.advanceTimersByTimeAsync(0); // let React Query deliver its update
    }
  });

describe('useSessionStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockApiFetch.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('polls every 3 s and stops once the session is complete', async () => {
    mockApiFetch
      .mockResolvedValueOnce(session('processing'))
      .mockResolvedValueOnce(session('processing'))
      .mockResolvedValue(session('complete'));

    const { result } = setup();
    await advance(0);
    expect(result.current.status).toBe('processing');
    expect(mockApiFetch).toHaveBeenCalledTimes(1);

    await advance(POLL_INTERVAL_MS);
    expect(mockApiFetch).toHaveBeenCalledTimes(2);

    await advance(POLL_INTERVAL_MS);
    expect(mockApiFetch).toHaveBeenCalledTimes(3);
    await vi.waitFor(() => expect(result.current.status).toBe('complete'));
    expect(result.current.isDone).toBe(true);

    await advance(POLL_INTERVAL_MS * 10);
    expect(mockApiFetch).toHaveBeenCalledTimes(3);
    expect(result.current.timedOut).toBe(false);
  });

  it('stops when the session has failed', async () => {
    mockApiFetch.mockResolvedValueOnce(session('processing')).mockResolvedValue(session('failed'));

    const { result } = setup();
    await advance(0);
    await advance(POLL_INTERVAL_MS);
    await vi.waitFor(() => expect(result.current.status).toBe('failed'));

    await advance(POLL_INTERVAL_MS * 10);
    expect(mockApiFetch).toHaveBeenCalledTimes(2);
  });

  it('gives up with timedOut after the timeout', async () => {
    mockApiFetch.mockResolvedValue(session('processing'));

    const { result } = setup();
    await advance(POLL_TIMEOUT_MS + POLL_INTERVAL_MS);
    expect(result.current.timedOut).toBe(true);
    expect(result.current.isDone).toBe(false);

    const calls = mockApiFetch.mock.calls.length;
    await advance(POLL_INTERVAL_MS * 10);
    expect(mockApiFetch).toHaveBeenCalledTimes(calls);
  });

  it('stops polling on an error such as 404', async () => {
    mockApiFetch.mockRejectedValue(Object.assign(new Error('Not found'), { status: 404 }));

    const { result } = setup();
    await advance(0);
    expect(result.current.error).toBeTruthy();

    await advance(POLL_INTERVAL_MS * 10);
    expect(mockApiFetch).toHaveBeenCalledTimes(1);
    expect(result.current.timedOut).toBe(false);
  });

  it('does not fetch without a session id', async () => {
    setup({});
    await advance(POLL_INTERVAL_MS * 3);
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});
