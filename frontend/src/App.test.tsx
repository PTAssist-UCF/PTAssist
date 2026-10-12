import { cloneElement, type ReactElement, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import App from './App';
import { setTokenGetter } from '@/apiClient';

/** The ClerkProvider settings that App.tsx passes, which the fake keeps for the tests. */
type ClerkSettings = {
  routerPush: (to: string) => unknown;
  routerReplace: (to: string) => unknown;
  signInUrl: string;
  signUpUrl: string;
};

// A fake Clerk, so the tests need no network and no Clerk account. Each test sets
// whether Clerk has loaded and whether someone is signed in. (vi.hoisted runs before the
// imports above, which vi.mock needs.)
const clerk = vi.hoisted(() => {
  const fake = {
    status: 'ready' as 'loading' | 'ready' | 'error',
    isSignedIn: false,
    // Like Clerk's getToken: the user's session token, or null when nobody is signed in.
    getToken: async (): Promise<string | null> => (fake.isSignedIn ? 'clerk-session-token' : null),
    signOut: vi.fn(),
    settings: null as ClerkSettings | null,
  };
  return fake;
});

vi.mock('@clerk/react', () => ({
  ClerkProvider: ({ children, ...settings }: ClerkSettings & { children: ReactNode }) => {
    clerk.settings = settings;
    return children;
  },
  useAuth: () => ({
    isLoaded: clerk.status === 'ready',
    isSignedIn: clerk.status === 'ready' ? clerk.isSignedIn : undefined,
    getToken: clerk.getToken,
  }),
  useClerk: () => ({ status: clerk.status }),
  // Like Clerk's forms: the fallback shows until Clerk has loaded.
  SignIn: ({ fallback }: { fallback?: ReactNode }) =>
    clerk.status === 'ready' ? 'Clerk sign-in form' : fallback,
  SignUp: ({ fallback }: { fallback?: ReactNode }) =>
    clerk.status === 'ready' ? 'Clerk sign-up form' : fallback,
  // Like Clerk's SignOutButton: clicking the button inside it signs out.
  SignOutButton: ({
    children,
    redirectUrl,
  }: {
    children: ReactElement<{ onClick: () => void }>;
    redirectUrl?: string;
  }) => cloneElement(children, { onClick: () => clerk.signOut({ redirectUrl }) }),
}));

// The app's settings. Some tests change the Clerk key.
const env = vi.hoisted(() => ({ apiUrl: 'http://api.test', clerkPublishableKey: '' }));
vi.mock('@/config/env', () => ({ env }));

const ME = {
  id: '3f6c1a52-8e0b-4d4e-9a77-2c1d5b9e0f41',
  email: 'pat@example.com',
  role: 'patient',
};

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

/** Opens the app at this address, wrapped the way main.tsx wraps it. */
function renderApp(path: string) {
  window.history.replaceState(null, '', path);
  // retry: false, so a failed request fails at once instead of being retried.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const app = () => (
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <App />
      </MantineProvider>
    </QueryClientProvider>
  );
  const view = render(app());
  // Draws the app again, as Clerk does when someone signs in or out.
  const rerenderApp = () => view.rerender(app());
  return { queryClient, rerenderApp };
}

/** Waits a moment, so a request the app has started would reach fetch. */
function waitAMoment() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

/** The fake API of the current test. */
let api: ReturnType<typeof fakeApi>;

beforeEach(() => {
  clerk.status = 'ready';
  clerk.isSignedIn = false;
  clerk.signOut.mockReset();
  clerk.settings = null;
  env.clerkPublishableKey = 'pk_test_unit-tests';
  // Every test gets a fake API, so none can reach the network. Tests can swap it.
  api = fakeApi(200, ME);
  vi.stubGlobal('fetch', api);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setTokenGetter(async () => null);
});

describe('sign-in', () => {
  it('sends a signed-out visitor to sign-in, and remembers where they were going', async () => {
    const historyLength = window.history.length;

    renderApp('/therapist?tab=plans');

    expect(await screen.findByText('Clerk sign-in form')).toBeDefined();
    expect(window.location.pathname).toBe('/sign-in');
    // Clerk sends the user back to redirect_url after they sign in.
    const redirectUrl = new URLSearchParams(window.location.search).get('redirect_url');
    expect(redirectUrl).toBe('/therapist?tab=plans');
    // Replaced, not added: the Back button doesn't return to the page and bounce again.
    expect(window.history.length).toBe(historyLength);
    expect(screen.queryByText('Therapist Dashboard')).toBeNull();
    expect(api).not.toHaveBeenCalled();
  });

  it('shows the page to a signed-in user, and API requests carry their Clerk token', async () => {
    clerk.isSignedIn = true;

    renderApp('/patient');

    // The account bar shows the email that GET /me returned.
    expect(await screen.findByText('Signed in as pat@example.com')).toBeDefined();
    expect(screen.getByText('Patient Portal')).toBeDefined();
    const [url, init] = api.mock.calls[0];
    expect(url).toBe('http://api.test/me');
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer clerk-session-token');
  });

  it('shows a spinner while Clerk loads, not the page', async () => {
    clerk.status = 'loading';

    renderApp('/patient');
    await waitAMoment();

    expect(document.querySelector('.mantine-Loader-root')).not.toBeNull();
    expect(screen.queryByText('Patient Portal')).toBeNull();
    expect(window.location.pathname).toBe('/patient');
    expect(api).not.toHaveBeenCalled();
  });

  it('says so when Clerk cannot load', () => {
    clerk.status = 'error';

    renderApp('/patient');

    expect(screen.getByText('Sign-in could not load')).toBeDefined();
    expect(screen.queryByText('Patient Portal')).toBeNull();
  });

  it('shows a spinner on the sign-in page until Clerk loads, or an error if it cannot', () => {
    clerk.status = 'loading';
    renderApp('/sign-in');
    expect(document.querySelector('.mantine-Loader-root')).not.toBeNull();
    expect(screen.queryByText('Clerk sign-in form')).toBeNull();
    cleanup();

    clerk.status = 'error';
    renderApp('/sign-in');
    expect(screen.getByText('Sign-in could not load')).toBeDefined();
  });

  it.each([
    ['missing', ''],
    ['the secret key by mistake', 'sk_test_oops'],
  ])('says what is wrong when the Clerk key is %s', (_, key) => {
    env.clerkPublishableKey = key;

    renderApp('/patient');

    expect(screen.getByText('Sign-in is not set up')).toBeDefined();
    expect(screen.queryByText('Patient Portal')).toBeNull();
  });

  it.each([
    ['/sign-in/factor-one', 'Clerk sign-in form'],
    ['/sign-up', 'Clerk sign-up form'],
    ['/sign-up/verify-email-address', 'Clerk sign-up form'],
  ])("keeps Clerk's form on %s", (path, form) => {
    renderApp(path);

    expect(screen.getByText(form)).toBeDefined();
    expect(window.location.pathname).toBe(path);
  });

  it('lets Clerk change pages through React Router, without reloading the app', async () => {
    renderApp('/sign-in');
    const settings = clerk.settings!;
    expect(settings.signInUrl).toBe('/sign-in');
    expect(settings.signUpUrl).toBe('/sign-up');
    const historyLength = window.history.length;

    // Clerk's "Sign up" link: a new page in the history.
    await act(async () => settings.routerPush('/sign-up'));
    expect(screen.getByText('Clerk sign-up form')).toBeDefined();
    expect(window.history.length).toBe(historyLength + 1);

    // A Clerk redirect that replaces the current page.
    await act(async () => settings.routerReplace('/sign-in'));
    expect(screen.getByText('Clerk sign-in form')).toBeDefined();
    expect(window.history.length).toBe(historyLength + 1);
  });

  it("shows the API's explanation when GET /me fails", async () => {
    clerk.isSignedIn = true;
    // What the API answers when its Clerk secret key is missing (a setup mistake).
    const detail =
      "CLERK_SECRET_KEY is not set on the API, so sign-in can't work. See /.env.example.";
    vi.stubGlobal('fetch', fakeApi(500, { detail }));

    renderApp('/patient');

    expect(
      await screen.findByText(`Could not load your account. The API answered 500: ${detail}`),
    ).toBeDefined();
  });

  it('shows the status alone when the API gives no explanation', async () => {
    clerk.isSignedIn = true;
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () => new Response('Bad Gateway', { status: 502 })),
    );

    renderApp('/patient');

    expect(
      await screen.findByText('Could not load your account. The API answered 502.'),
    ).toBeDefined();
  });

  it('says so when the API does not answer at all', async () => {
    clerk.isSignedIn = true;
    // What fetch does when the API is down or the browser blocks the answer (CORS).
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () => {
        throw new TypeError('Failed to fetch');
      }),
    );

    renderApp('/patient');

    expect(
      await screen.findByText('Could not load your account: no answer from the API.'),
    ).toBeDefined();
  });
});

describe('sign-out', () => {
  it('signs out through Clerk, and asks it to open the sign-in page', async () => {
    clerk.isSignedIn = true;
    renderApp('/patient');

    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }));

    expect(clerk.signOut).toHaveBeenCalledWith({ redirectUrl: '/sign-in' });
  });

  it("forgets the cached API answers, so the next user never sees the last user's data", async () => {
    clerk.isSignedIn = true;
    const { queryClient, rerenderApp } = renderApp('/patient');
    await screen.findByText('Signed in as pat@example.com');
    expect(queryClient.getQueryData(['/me'])).toEqual(ME);

    // Signed out (by the button, an expired session, or another tab).
    clerk.isSignedIn = false;
    rerenderApp();

    expect(await screen.findByText('Clerk sign-in form')).toBeDefined();
    await waitFor(() => expect(queryClient.getQueryCache().getAll()).toHaveLength(0));
  });
});
