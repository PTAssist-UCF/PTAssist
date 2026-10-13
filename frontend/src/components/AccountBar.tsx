import { Button, Container, Group, Text } from '@mantine/core';
import { SignOutButton } from '@clerk/react';

import { useGetMe } from '@/api/me';
import { ApiError } from '@/apiClient';

/**
 * A bar above every signed-in page: who is signed in, and a Sign out button.
 *
 * The email comes from the API (GET /me, sent with the user's Clerk token), so seeing it
 * shows that sign-in reaches the backend. The app shell (SCRUM-56) will replace this bar.
 */
export default function AccountBar() {
  // Only rendered for a signed-in user (inside RequireSignIn), so the request has a token.
  const { data: me, error } = useGetMe();

  return (
    <Container size="lg" pt="md">
      <Group justify="flex-end" gap="sm">
        {me && (
          <Text size="sm" c="dimmed">
            Signed in as {me.email}
          </Text>
        )}
        {error && (
          <Text size="sm" c="red">
            {describeError(error)}
          </Text>
        )}
        {/* Clerk's sign-out, on a Mantine button. Clerk then opens the sign-in page. */}
        <SignOutButton redirectUrl="/sign-in">
          <Button variant="default" size="xs">
            Sign out
          </Button>
        </SignOutButton>
      </Group>
    </Container>
  );
}

/**
 * Why GET /me failed, with the API's own explanation when it gave one. For example,
 * when the API has no Clerk secret key, it answers 500 and says so.
 */
function describeError(error: Error): string {
  if (!(error instanceof ApiError)) {
    // No answer the browser could read: the API is down, or CORS blocked it.
    return 'Could not load your account: no answer from the API.';
  }
  // FastAPI errors look like { "detail": "..." }.
  const detail = (error.body as { detail?: unknown } | undefined)?.detail;
  const explanation = typeof detail === 'string' ? `: ${detail}` : '.';
  return `Could not load your account. The API answered ${error.status}${explanation}`;
}
