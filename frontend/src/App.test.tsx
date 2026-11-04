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
    signOut: clerk.signOut,
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

describe('app shell and role navigation', () => {
  it('renders the patient shell with patient navigation for a patient', async () => {
    clerk.isSignedIn = true;
    api = fakeApi(200, { ...ME, role: 'patient' });
    vi.stubGlobal('fetch', api);

    renderApp('/patient');

    expect(await screen.findByText('Signed in as pat@example.com')).toBeDefined();
    expect(screen.getByText('PTAssist')).toBeDefined();
    expect(screen.getByText('Patient')).toBeDefined();
    expect(screen.queryByText('Therapist')).toBeNull();

    // Patient navigation items
    expect(screen.getByRole('link', { name: /my plan/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /upload video/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /results & history/i })).toBeDefined();

    // Therapist navigation items should not be present
    expect(screen.queryByRole('link', { name: /patients/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /plan builder/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /progress & analytics/i })).toBeNull();

    // Main page content
    expect(screen.getByText('Patient Portal')).toBeDefined();
    expect(screen.getByText('My Exercise Plan')).toBeDefined();
  });

  it('renders the therapist shell with therapist navigation for a therapist', async () => {
    clerk.isSignedIn = true;
    api = fakeApi(200, { ...ME, role: 'therapist' });
    vi.stubGlobal('fetch', api);

    renderApp('/therapist');

    expect(await screen.findByText('Signed in as pat@example.com')).toBeDefined();
    expect(screen.getByText('PTAssist')).toBeDefined();
    expect(screen.getByText('Therapist')).toBeDefined();
    expect(screen.queryByText('Patient')).toBeNull();

    // Therapist navigation items
    expect(screen.getByRole('link', { name: /patients/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /plan builder/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /progress & analytics/i })).toBeDefined();

    // Patient navigation items should not be present
    expect(screen.queryByRole('link', { name: /my plan/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /upload video/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /results & history/i })).toBeNull();

    // Main page content
    expect(screen.getByText('Therapist Dashboard')).toBeDefined();
    expect(screen.getByText('Assigned Patients')).toBeDefined();
    expect(screen.getByText('+ Link New Patient')).toBeDefined();
  });

  it('highlights the active navigation link when visiting role subroutes', async () => {
    clerk.isSignedIn = true;
    api = fakeApi(200, { ...ME, role: 'patient' });
    vi.stubGlobal('fetch', api);

    renderApp('/patient/upload');
    expect(await screen.findByText('Signed in as pat@example.com')).toBeDefined();
    const uploadLink = screen.getByRole('link', { name: /upload video/i });
    expect(uploadLink.getAttribute('data-active')).toBe('true');

    cleanup();

    api = fakeApi(200, { ...ME, role: 'therapist' });
    vi.stubGlobal('fetch', api);

    renderApp('/therapist/plans');
    expect(await screen.findByText('Signed in as pat@example.com')).toBeDefined();
    const plansLink = screen.getByRole('link', { name: /plan builder/i });
    expect(plansLink.getAttribute('data-active')).toBe('true');
  });

  it.each([
    ['patient', '/patient/upload', 'Upload Video'],
    ['patient', '/patient/history', 'Results & History'],
    ['therapist', '/therapist/plans', 'Plan Builder'],
    ['therapist', '/therapist/progress', 'Progress & Analytics'],
  ])('shows a "Coming soon" page for the %s page %s', async (role, path, title) => {
    clerk.isSignedIn = true;
    api = fakeApi(200, { ...ME, role });
    vi.stubGlobal('fetch', api);

    renderApp(path);

    expect(await screen.findByRole('heading', { name: title })).toBeDefined();
    expect(screen.getByText('Coming soon.')).toBeDefined();
    // Not the main page of that side.
    expect(screen.queryByText('My Exercise Plan')).toBeNull();
    expect(screen.queryByText('Assigned Patients')).toBeNull();
  });

  it('hides the email on phone widths, so Sign out still fits in the header', async () => {
    clerk.isSignedIn = true;

    renderApp('/patient');

    const email = await screen.findByText('Signed in as pat@example.com');
    expect(email.classList.contains('mantine-visible-from-sm')).toBe(true);
  });

  it('does not guess the role from the address while /me loads', async () => {
    clerk.isSignedIn = true;
    vi.stubGlobal('fetch', () => new Promise(() => {}));

    renderApp('/therapist');
    await waitAMoment();

    expect(document.querySelectorAll('.mantine-Skeleton-root').length).toBeGreaterThan(0);
    expect(screen.queryByText('Therapist')).toBeNull();
    expect(screen.queryByText('Therapist Dashboard')).toBeNull();
    expect(screen.queryByRole('link', { name: /plan builder/i })).toBeNull();
  });

  it('shows no role-specific navigation when /me fails', async () => {
    clerk.isSignedIn = true;
    vi.stubGlobal('fetch', fakeApi(500, { detail: 'Server error' }));

    renderApp('/therapist');

    expect(
      await screen.findByText('Could not load your account. The API answered 500: Server error'),
    ).toBeDefined();
    expect(screen.getByText('Navigation is unavailable until your account loads.')).toBeDefined();
    expect(screen.queryByText('Therapist')).toBeNull();
    expect(screen.queryByText('Patient')).toBeNull();
    expect(screen.queryByText('Therapist Dashboard')).toBeNull();
    expect(screen.queryByText('Patient Portal')).toBeNull();
    // The error from RoleRedirect, which RoleRoute sends the user to.
    expect(await screen.findByText("Couldn't load your account.")).toBeDefined();
  });

  it('shows loading skeletons in the shell while user account is loading', async () => {
    clerk.isSignedIn = true;
    vi.stubGlobal('fetch', () => new Promise(() => {}));

    renderApp('/patient');
    await waitAMoment();

    expect(screen.getByText('PTAssist')).toBeDefined();
    expect(document.querySelectorAll('.mantine-Skeleton-root').length).toBeGreaterThan(0);
    expect(screen.queryByText('Signed in as pat@example.com')).toBeNull();
  });
});

describe('session expiration (401)', () => {
  it('signs out of Clerk and returns to the page after sign-in, for a patient', async () => {
    clerk.isSignedIn = true;
    api = fakeApi(401, { detail: 'Token expired' });
    vi.stubGlobal('fetch', api);

    renderApp('/patient');

    // Signing out first matters: Clerk's sign-in page would send a still-signed-in user
    // straight back to redirect_url, which would answer 401 again, in a loop.
    await waitFor(() =>
      expect(clerk.signOut).toHaveBeenCalledWith({
        redirectUrl: `/sign-in?redirect_url=${encodeURIComponent('/patient')}`,
      }),
    );
    expect(screen.queryByText('My Exercise Plan')).toBeNull();
  });

  it('signs out of Clerk and returns to the page after sign-in, for a therapist', async () => {
    clerk.isSignedIn = true;
    api = fakeApi(401, { detail: 'Token expired' });
    vi.stubGlobal('fetch', api);

    renderApp('/therapist?tab=analytics#top');

    await waitFor(() =>
      expect(clerk.signOut).toHaveBeenCalledWith({
        redirectUrl: `/sign-in?redirect_url=${encodeURIComponent('/therapist?tab=analytics#top')}`,
      }),
    );
    expect(screen.queryByText('Assigned Patients')).toBeNull();
  });

  it('does not keep asking the API while Clerk signs out', async () => {
    clerk.isSignedIn = true;
    api = fakeApi(401, { detail: 'Token expired' });
    vi.stubGlobal('fetch', api);

    renderApp('/patient');
    await waitFor(() => expect(clerk.signOut).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(api).toHaveBeenCalledTimes(1);
    expect(clerk.signOut).toHaveBeenCalledTimes(1);
  });
});
