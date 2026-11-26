/**
 * What the patient detail page and the session result page show in place of their
 * content: a loading message, a request that failed (with a Try again button), or why a
 * patient or a session can't be shown (with a link back).
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Anchor, Button, Group, Loader, Stack, Text } from '@mantine/core';

import { describeApiError } from '@/utils/apiErrors';

/** A spinner, and what is loading. */
export function LoadingMessage({ children }: { children: ReactNode }) {
  return (
    <Group justify="center" gap="sm" py="xl" role="status">
      <Loader size="sm" />
      <Text c="dimmed">{children}</Text>
    </Group>
  );
}

/** A request that failed: the API's answer, and a button to send it again. */
export function LoadErrorAlert({
  title,
  error,
  retrying,
  onRetry,
}: {
  title: string;
  error: Error;
  /** True while the request is sent again. */
  retrying: boolean;
  onRetry: () => void;
}) {
  return (
    <Alert color="red" title={title}>
      <Stack gap="xs" align="flex-start">
        <Text size="sm">{describeApiError(error)}</Text>
        <Button size="xs" variant="default" loading={retrying} onClick={onRetry}>
          Try again
        </Button>
      </Stack>
    </Alert>
  );
}

/** Why something can't be shown, and a link to where the therapist can go instead. */
export function NotFoundAlert({
  title,
  children,
  backTo,
  backLabel,
}: {
  title: string;
  children: ReactNode;
  backTo: string;
  backLabel: string;
}) {
  return (
    <Alert color="yellow" title={title}>
      {children}{' '}
      <Anchor component={Link} to={backTo} size="sm">
        {backLabel}
      </Anchor>
      .
    </Alert>
  );
}

/**
 * The patient isn't one of the therapist's linked patients (an unknown id, another
 * therapist's patient), or the API no longer shows their sessions (403 or 404).
 */
export function PatientNotFound() {
  return (
    <NotFoundAlert title="Patient not found" backTo="/therapist" backLabel="Back to your patients">
      You can&apos;t see this patient&apos;s sessions.
    </NotFoundAlert>
  );
}
