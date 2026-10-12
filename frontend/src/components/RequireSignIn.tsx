import { Center } from '@mantine/core';
import { useAuth } from '@clerk/react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import AccountBar from '@/components/AccountBar';
import AuthLoading from '@/components/AuthLoading';

/**
 * A layout route for the pages that need a signed-in user (see App.tsx).
 *
 * - While Clerk loads, it shows a spinner (or an error if Clerk can't load).
 * - A signed-out visitor goes to /sign-in, and comes back to this page after signing in.
 * - A signed-in user sees the page, with the account bar above it.
 *
 * This only keeps the screens tidy. The API checks the token on every request.
 */
export default function RequireSignIn() {
  const { isLoaded, isSignedIn } = useAuth();
  const location = useLocation();

  if (!isLoaded) {
    return (
      <Center mih="100vh" p="md">
        <AuthLoading />
      </Center>
    );
  }

  if (!isSignedIn) {
    // Clerk's sign-in page sends the user back to redirect_url once they are signed in.
    // "replace" keeps the Back button from returning to this page and bouncing again.
    // This also runs right after Sign out, so the sign-in page then remembers the page
    // the last user was on.
    const here = location.pathname + location.search + location.hash;
    return <Navigate to={`/sign-in?redirect_url=${encodeURIComponent(here)}`} replace />;
  }

  return (
    <>
      <AccountBar />
      <Outlet />
    </>
  );
}
