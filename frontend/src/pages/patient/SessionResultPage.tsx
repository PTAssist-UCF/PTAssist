import { useEffect, useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Container,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  Title,
} from '@mantine/core';

import { getGetSessionResultQueryKey, useGetSessionResult } from '@/api/results';
import { ApiError } from '@/apiClient';
import { ResultView } from '@/components/ResultView/ResultView';
import { useSessionStatus } from '@/hooks/useSessionStatus';
import { describeApiError } from '@/utils/apiErrors';
import { uploadPath } from './planDisplay';
import { HISTORY_PATH, STATUS_BADGE, formatDateTime } from './sessionDisplay';

/**
 * One session's result (/patient/history/:sessionId), from GET /sessions/{id}/result,
 * shown with ResultView. The upload page opens it after an upload, and Results & History
 * links to it.
 *
 * While the session is processing, its result is null: the page polls the session's
 * status (useSessionStatus) and loads the result once the analysis has finished.
 */
export default function SessionResultPage() {
  const { sessionId = '' } = useParams();
  const navigate = useNavigate();
  const { data: session, error, isFetching, refetch } = useGetSessionResult(sessionId);
  // Counts "Check again" and "Try again" while waiting: each one starts the polling over.
  const [attempt, setAttempt] = useState(0);

  let content: ReactNode;
  if (session?.result) {
    // complete or failed. A failed result shows its message, and a re-upload for this
    // exercise unless its error_code is unknown_exercise (ResultView decides).
    content = (
      <ResultView
        result={session.result}
        onReupload={() => navigate(uploadPath(session.plan_exercise_id))}
      />
    );
  } else if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
    // 404: no such session, or another patient's (the API gives both the same answer).
    // 422: the id in the address isn't a session id at all.
    content = (
      <Alert color="gray" title="Session not found">
        This session doesn't exist, or it isn't one of yours.{' '}
        <Anchor component={Link} to={HISTORY_PATH}>
          See all your results
        </Anchor>
        .
      </Alert>
    );
  } else if (error) {
    content = (
      <Alert color="red" title="Could not load this result">
        <Stack gap="xs" align="flex-start">
          <Text size="sm">{describeApiError(error)}</Text>
          <Button size="xs" variant="default" loading={isFetching} onClick={() => void refetch()}>
            Try again
          </Button>
        </Stack>
      </Alert>
    );
  } else if (!session) {
    content = (
      <Group justify="center" gap="sm" py="xl" role="status">
        <Loader size="sm" />
        <Text c="dimmed">Loading your result...</Text>
      </Group>
    );
  } else {
    // Still processing.
    content = (
      <WaitForResult
        key={attempt}
        sessionId={session.id}
        onRetry={() => setAttempt((count) => count + 1)}
      />
    );
  }

  const badge = session && STATUS_BADGE[session.status];
  return (
    <Container size="md" py="lg">
      <Stack gap="lg">
        <Anchor component={Link} to={HISTORY_PATH} size="sm">
          All results
        </Anchor>

        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={1} size="h2">
              {session ? session.exercise_display_name : 'Result'}
            </Title>
            {session && (
              <Text c="dimmed" component="time" dateTime={session.created_at}>
                {formatDateTime(session.created_at)}
              </Text>
            )}
          </div>
          {badge && (
            <Badge color={badge.color} variant="light" size="lg">
              {badge.label}
            </Badge>
          )}
        </Group>

        {content}

        <Group justify="flex-end">
          <Button variant="default" component={Link} to="/patient">
            Back to Plan
          </Button>
        </Group>
      </Stack>
    </Container>
  );
}

/**
 * Shown while the session is processing: polls its status every few seconds
 * (useSessionStatus), and once the analysis has finished, loads the result, which then
 * replaces this. onRetry starts the polling over, after it timed out or failed.
 */
function WaitForResult({ sessionId, onRetry }: { sessionId: string; onRetry: () => void }) {
  const queryClient = useQueryClient();
  const { isDone, timedOut, error } = useSessionStatus(sessionId);

  useEffect(() => {
    if (isDone) {
      void queryClient.invalidateQueries({ queryKey: getGetSessionResultQueryKey(sessionId) });
    }
  }, [isDone, queryClient, sessionId]);

  if (timedOut) {
    return (
      <Alert color="yellow" title="This is taking longer than usual">
        <Stack gap="xs" align="flex-start">
          <Text size="sm">
            Your video is still being analyzed. Its result will be in Results & History once it is
            ready.
          </Text>
          <Button size="xs" variant="default" onClick={onRetry}>
            Check again
          </Button>
        </Stack>
      </Alert>
    );
  }

  if (error) {
    return (
      <Alert color="red" title="Could not check on your video">
        <Stack gap="xs" align="flex-start">
          <Text size="sm">{describeApiError(error)}</Text>
          <Button size="xs" variant="default" onClick={onRetry}>
            Try again
          </Button>
        </Stack>
      </Alert>
    );
  }

  return (
    <Paper withBorder p="lg" radius="md">
      <Group gap="md" wrap="nowrap" role="status">
        <Loader size="sm" />
        <div>
          <Text fw={600}>Analyzing your video...</Text>
          <Text size="sm" c="dimmed">
            This can take a few minutes. Your result will show here when it is ready. You can leave
            this page: it will also be in Results & History.
          </Text>
        </div>
      </Group>
    </Paper>
  );
}
