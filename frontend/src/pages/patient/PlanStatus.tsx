import { Alert, Button, Group, Loader, Stack, Text } from '@mantine/core';

import { ApiError } from '@/apiClient';

interface PlanStatusProps {
  /** From useGetMyPlan(): no answer yet. */
  isPending: boolean;
  /** From useGetMyPlan(): a request is under way, for example after "Try again". */
  isFetching: boolean;
  /** From useGetMyPlan(). A 404 means the patient has no plan yet. */
  error: unknown;
  onRetry: () => void;
}

/**
 * What the patient pages show when they have no exercises to list: a spinner while the
 * plan loads, a note when there is no plan yet (GET /plans/me answers 404), or the error
 * with a "Try again" button.
 */
export default function PlanStatus({ isPending, isFetching, error, onRetry }: PlanStatusProps) {
  if (isPending) {
    return (
      <Group justify="center" gap="sm" py="xl" role="status">
        <Loader size="sm" />
        <Text c="dimmed">Loading your plan...</Text>
      </Group>
    );
  }

  const noPlanYet = error instanceof ApiError && error.status === 404;
  if (error && !noPlanYet) {
    return (
      <Alert color="red" title="Could not load your plan">
        <Stack gap="xs" align="flex-start">
          <Text size="sm">{describeError(error)}</Text>
          <Button size="xs" variant="default" loading={isFetching} onClick={onRetry}>
            Try again
          </Button>
        </Stack>
      </Alert>
    );
  }

  // No plan yet. A plan always has at least one exercise (the API refuses to save an
  // empty one), but an empty list would get this note too.
  return (
    <Alert color="gray" title="Your therapist hasn't assigned a plan yet">
      Once they do, your exercises will show up here, and you can upload a video for each one.
    </Alert>
  );
}

/** Explains why the plan didn't load, with the API's own message when it has one. */
function describeError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return 'No answer from the API. Check your connection, then try again.';
  }
  const detail = (error.body as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string'
    ? `The API answered ${error.status}: ${detail}`
    : `The API answered ${error.status}.`;
}
