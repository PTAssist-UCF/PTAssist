import { useEffect, type ReactNode } from 'react';
import { useAuth } from '@clerk/react';
import { useQueryClient } from '@tanstack/react-query';

import { setTokenGetter } from '@/apiClient';

/**
 * Connects the API client (src/apiClient.ts) to Clerk:
 *
 * - Every API request carries the signed-in user's Clerk token.
 * - When nobody is signed in, the cached API answers are forgotten, so the next person
 *   to sign in on this browser never sees the previous user's data. This covers every
 *   way of being signed out: the Sign out button, an expired session, or signing out in
 *   another tab.
 *
 * Render it inside ClerkProvider and QueryClientProvider, around the routes (App.tsx).
 */
export default function ApiAuth({ children }: { children: ReactNode }) {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const queryClient = useQueryClient();

  // Set while rendering, not in a useEffect, so the token getter is in place before any
  // page below sends its first request (a parent's effects run after its children's).
  // Clerk's getToken waits until Clerk has loaded, gives null when nobody is signed in,
  // and refreshes the token (valid for 60 seconds) by itself.
  setTokenGetter(getToken);

  useEffect(() => {
    // When this runs, the signed-in pages are already gone from the screen
    // (RequireSignIn sent the user to sign in), so nothing still shows the old answers.
    if (isLoaded && !isSignedIn) {
      queryClient.clear();
    }
  }, [isLoaded, isSignedIn, queryClient]);

  return children;
}
