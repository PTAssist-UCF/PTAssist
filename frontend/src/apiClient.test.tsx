import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { useGetMe } from '@/api/me';
import { ApiError, setTokenGetter, setUnauthorizedHandler, uploadWithProgress } from '@/apiClient';
import ApiAuth from '@/components/ApiAuth';
import { shouldRetryQuery } from '@/main';

// A fake Clerk for the ApiAuth tests: always signed in, with a signOut to check.
const clerk = vi.hoisted(() => ({ signOut: vi.fn(async () => {}) }));
vi.mock('@clerk/react', () => ({
  useAuth: () => ({
    isLoaded: true,
    isSignedIn: true,
    getToken: async () => 'clerk-session-token',
    signOut: clerk.signOut,
  }),
}));

const ME = { id: '3f6c1a52-8e0b-4d4e-9a77-2c1d5b9e0f41', email: 'pat@example.com' };

/** A fake fetch that always gives this answer, so the tests need no backend. */
function fakeApi(status: number, body: unknown) {
  return vi.fn<typeof fetch>(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
  );
}

/** Runs useGetMe the way the app does: inside a QueryClientProvider. */
function renderUseGetMe() {
  // retry: false, so a failed request fails at once instead of being retried.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useGetMe(), { wrapper });
}

afterEach(() => {
  cleanup();
  clerk.signOut.mockClear();
  vi.unstubAllGlobals();
  setTokenGetter(async () => null);
  setUnauthorizedHandler(() => {});
});

describe('useGetMe', () => {
  it("returns the signed-in user's role", async () => {
    vi.stubGlobal('fetch', fakeApi(200, { ...ME, role: 'therapist' }));

    const { result } = renderUseGetMe();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.role).toBe('therapist');
  });

  it("calls GET /me at the API's address with the user's token", async () => {
    const fetch = fakeApi(200, { ...ME, role: 'patient' });
    vi.stubGlobal('fetch', fetch);
    setTokenGetter(async () => 'test-token');

    const { result } = renderUseGetMe();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [url, init] = fetch.mock.calls[0];
    // vite.config.ts sets VITE_API_URL to 'http://api.test/' for tests.
    expect(url).toBe('http://api.test/me');
    expect(init?.method).toBe('GET');
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer test-token');
  });

  it('sends no token when nobody is signed in', async () => {
    const fetch = fakeApi(200, { ...ME, role: 'patient' });
    vi.stubGlobal('fetch', fetch);

    const { result } = renderUseGetMe();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [, init] = fetch.mock.calls[0];
    expect(new Headers(init?.headers).has('Authorization')).toBe(false);
  });

  it('reports an error answer as an ApiError with its status', async () => {
    vi.stubGlobal('fetch', fakeApi(401, { detail: 'Missing bearer token' }));

    const { result } = renderUseGetMe();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error?.status).toBe(401);
    expect(result.current.error?.body).toEqual({ detail: 'Missing bearer token' });
    expect(result.current.data).toBeUndefined();
  });

  it('keeps the status when an error answer has a broken JSON body', async () => {
    const brokenBody = '<html>502 Bad Gateway</html>';
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(
        async () =>
          new Response(brokenBody, {
            status: 502,
            headers: { 'Content-Type': 'application/json' },
          }),
      ),
    );

    const { result } = renderUseGetMe();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error?.status).toBe(502);
    expect(result.current.error?.body).toBe(brokenBody);
  });

  it('invokes the unauthorized handler when the API returns 401', async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    vi.stubGlobal('fetch', fakeApi(401, { detail: 'Session expired' }));

    const { result } = renderUseGetMe();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('does not invoke the unauthorized handler on non-401 responses', async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    vi.stubGlobal('fetch', fakeApi(403, { detail: 'Forbidden' }));

    const { result } = renderUseGetMe();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});

describe('ApiAuth on a 401 answer', () => {
  /** Runs useGetMe inside ApiAuth, as the app does, with the browser at this address. */
  function renderInsideApiAuth(path: string) {
    window.history.replaceState(null, '', path);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <ApiAuth>{children}</ApiAuth>
      </QueryClientProvider>
    );
    return { queryClient, ...renderHook(() => useGetMe(), { wrapper }) };
  }

  it('signs out of Clerk, then opens sign-in with the current page as redirect_url', async () => {
    vi.stubGlobal('fetch', fakeApi(401, { detail: 'Session expired' }));

    renderInsideApiAuth('/patient/history?week=2#latest');

    await waitFor(() => expect(clerk.signOut).toHaveBeenCalledTimes(1));
    expect(clerk.signOut).toHaveBeenCalledWith({
      redirectUrl: `/sign-in?redirect_url=${encodeURIComponent('/patient/history?week=2#latest')}`,
    });
  });

  it('empties the API cache', async () => {
    vi.stubGlobal('fetch', fakeApi(401, { detail: 'Session expired' }));
    const { queryClient } = renderInsideApiAuth('/patient');
    queryClient.setQueryData(['/plans'], ['cached plan']);

    await waitFor(() => expect(clerk.signOut).toHaveBeenCalled());
    expect(queryClient.getQueryData(['/plans'])).toBeUndefined();
  });

  it('does not sign out on other errors', async () => {
    vi.stubGlobal('fetch', fakeApi(403, { detail: 'Forbidden' }));

    const { result } = renderInsideApiAuth('/patient');

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(clerk.signOut).not.toHaveBeenCalled();
  });
});

describe('shouldRetryQuery', () => {
  it('does not retry 4xx client errors (e.g. 401, 403, 404)', () => {
    expect(shouldRetryQuery(0, new ApiError(400, {}))).toBe(false);
    expect(shouldRetryQuery(0, new ApiError(401, {}))).toBe(false);
    expect(shouldRetryQuery(0, new ApiError(403, {}))).toBe(false);
    expect(shouldRetryQuery(0, new ApiError(404, {}))).toBe(false);
  });

  it('retries server errors (5xx) and network errors up to 3 times', () => {
    const serverError = new ApiError(500, {});
    expect(shouldRetryQuery(0, serverError)).toBe(true);
    expect(shouldRetryQuery(1, serverError)).toBe(true);
    expect(shouldRetryQuery(2, serverError)).toBe(true);
    expect(shouldRetryQuery(3, serverError)).toBe(false);

    const networkError = new TypeError('Failed to fetch');
    expect(shouldRetryQuery(0, networkError)).toBe(true);
    expect(shouldRetryQuery(2, networkError)).toBe(true);
    expect(shouldRetryQuery(3, networkError)).toBe(false);
  });
});

describe('uploadWithProgress', () => {
  const originalXHR = window.XMLHttpRequest;

  class FakeXHR {
    static instance: FakeXHR;
    constructor() {
      FakeXHR.instance = this;
    }
    open = vi.fn();
    setRequestHeader = vi.fn();
    send = vi.fn();
    abort = vi.fn();
    status = 200;
    responseText = '{}';
    upload: { onprogress: ((ev: ProgressEvent) => void) | null } = { onprogress: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
  }

  beforeEach(() => {
    window.XMLHttpRequest = FakeXHR as unknown as typeof XMLHttpRequest;
  });

  afterEach(() => {
    window.XMLHttpRequest = originalXHR;
  });

  it('sends POST request to API URL with Clerk auth header and progress callbacks', async () => {
    setTokenGetter(async () => 'clerk-token');
    const onProgress = vi.fn();
    const formData = new FormData();
    formData.append('key', 'val');

    const promise = uploadWithProgress('/sessions', formData, { onProgress });

    await waitFor(() => expect(FakeXHR.instance).toBeDefined());
    const xhr = FakeXHR.instance;

    expect(xhr.open).toHaveBeenCalledWith('POST', 'http://api.test/sessions');
    expect(xhr.setRequestHeader).toHaveBeenCalledWith('Authorization', 'Bearer clerk-token');
    expect(xhr.send).toHaveBeenCalledWith(formData);

    xhr.upload.onprogress?.({
      lengthComputable: true,
      loaded: 40,
      total: 100,
    } as ProgressEvent);

    expect(onProgress).toHaveBeenCalledWith({ loaded: 40, total: 100, percent: 40 });

    xhr.status = 201;
    xhr.responseText = JSON.stringify({ id: 'sess-1', status: 'processing' });
    xhr.onload?.();

    const res = await promise;
    expect(res).toEqual({ id: 'sess-1', status: 'processing' });
  });

  it('invokes unauthorizedHandler on 401 responses', async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);

    const promise = uploadWithProgress('/sessions', new FormData());

    await waitFor(() => expect(FakeXHR.instance).toBeDefined());
    const xhr = FakeXHR.instance;

    xhr.status = 401;
    xhr.responseText = JSON.stringify({ detail: 'Token expired' });
    xhr.onload?.();

    await expect(promise).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('aborts upload when signal is triggered', async () => {
    const controller = new AbortController();
    const promise = uploadWithProgress('/sessions', new FormData(), {
      signal: controller.signal,
    });

    await waitFor(() => expect(FakeXHR.instance).toBeDefined());
    const xhr = FakeXHR.instance;

    controller.abort();

    expect(xhr.abort).toHaveBeenCalled();
    await expect(promise).rejects.toThrow('Upload aborted');
  });
});
