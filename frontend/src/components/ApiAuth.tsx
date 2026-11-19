import { useEffect, type ReactNode } from 'react';
import { useAuth } from '@clerk/react';
import { useQueryClient } from '@tanstack/react-query';

import { setTokenGetter, setUnauthorizedHandler } from '@/apiClient';

/**
 * Connects the API client (src/apiClient.ts) to Clerk:
 *
 * - Every API request carries the signed-in user's Clerk token.
 * - When nobody is signed in, the cached API answers are forgotten, so the next person
 *   to sign in on this browser never sees the previous user's data. This covers every
 *   way of being signed out: the Sign out button, an expired session, or signing out in
 *   another tab.
 * - When any API request returns 401, the cache is cleared and the user is signed out of
 *   Clerk, then sent to /sign-in with redirect_url pointing back to the current page.
 *   Signing out matters: a 401 while Clerk still says "signed in" means the API rejected
 *   a token Clerk thinks is valid (mismatched keys, clock drift, revoked session). Clerk's
 *   sign-in page sends a signed-in user straight back to redirect_url, so without the
 *   sign-out the app would loop between that page and /sign-in.
 *
 * Render it inside ClerkProvider and QueryClientProvider, around the routes (App.tsx).
 */
export default function ApiAuth({ children }: { children: ReactNode }) {
  const { getToken, isLoaded, isSignedIn, signOut } = useAuth();
  const queryClient = useQueryClient();

  // Set while rendering, not in a useEffect, so the token getter is in place before any
  // page below sends its first request (a parent's effects run after its children's).
  // Clerk's getToken waits until Clerk has loaded, gives null when nobody is signed in,
  // and refreshes the token (valid for 60 seconds) by itself.
  setTokenGetter(getToken);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      queryClient.clear();
      // Read the address when the 401 happens, so the handler needn't be registered
      // again on every page change.
      const here = window.location.pathname + window.location.search + window.location.hash;
      void signOut({ redirectUrl: `/sign-in?redirect_url=${encodeURIComponent(here)}` });
    });
    return () => {
      setUnauthorizedHandler(() => {});
    };
  }, [signOut, queryClient]);

  useEffect(() => {
    // When this runs, the signed-in pages are already gone from the screen
    // (RequireSignIn sent the user to sign in), so nothing still shows the old answers.
    if (isLoaded && !isSignedIn) {
      queryClient.clear();
    }
  }, [isLoaded, isSignedIn, queryClient]);

  return children;
}
