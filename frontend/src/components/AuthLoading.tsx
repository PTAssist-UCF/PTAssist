import { Alert, Loader } from '@mantine/core';
import { useClerk } from '@clerk/react';

/**
 * What to show until Clerk (sign-in) has loaded: a spinner.
 *
 * Clerk's code comes from Clerk's servers. If it can't be downloaded, Clerk gives up after
 * about 15 seconds, and this says so instead of spinning forever. The usual causes are no
 * internet, an ad blocker, or a wrong VITE_CLERK_PUBLISHABLE_KEY (the browser console then
 * says "Failed to load Clerk JS").
 */
export default function AuthLoading() {
  const { status } = useClerk();

  if (status === 'error') {
    return (
      <Alert color="red" title="Sign-in could not load">
        Check your internet connection, then reload the page.
      </Alert>
    );
  }
  return <Loader />;
}
