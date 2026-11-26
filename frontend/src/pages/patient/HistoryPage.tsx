import { useEffect, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Badge,
  Button,
  Card,
  Container,
  EmptyState,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  Title,
} from '@mantine/core';

import { useGetMe } from '@/api/me';
import type { ProgressPoint, SessionSummary } from '@/api/model';
import {
  getGetPatientProgressQueryKey,
  getListPatientSessionsQueryKey,
  useGetPatientProgress,
  useListPatientSessions,
} from '@/api/results';
import { BAND_COLOR, BAND_LABEL, getScoreBand } from '@/components/ResultView/scoreBand';
import { useSessionStatus } from '@/hooks/useSessionStatus';
import { describeApiError } from '@/utils/apiErrors';
import { STATUS_BADGE, describeCount, formatDateTime, resultPath } from './sessionDisplay';

/**
 * Results & History (/patient/history): the patient's sessions, newest first, from
 * GET /patients/{id}/sessions with their own id from GET /me. Each one opens its result
 * page. The numbers of complete sessions come from GET /patients/{id}/progress, because
 * the list has no results. A session still processing polls its status, and the list
 * loads again when its analysis has finished.
 */
export default function HistoryPage() {
  const { data: me } = useGetMe();
  const patientId = me?.id ?? '';
  const query = {
    enabled: Boolean(me),
    // Asked again every time the page opens, even when the cached answer is fresh, so a
    // video uploaded since then shows up.
    refetchOnMount: 'always',
  } as const;
  const sessions = useListPatientSessions(patientId, { query });
  const progress = useGetPatientProgress(patientId, { query });

  // Each complete session's numbers, by session id.
  const points = new Map<string, ProgressPoint>();
  for (const exercise of progress.data ?? []) {
    for (const point of exercise.sessions) {
      points.set(point.session_id, point);
    }
  }

  let content: ReactNode;
  if (!sessions.data) {
    // Not loaded yet. After it has loaded, a failed refetch keeps the last list on screen.
    content = sessions.error ? (
      <Alert color="red" title="Could not load your sessions">
        <Stack gap="xs" align="flex-start">
          <Text size="sm">{describeApiError(sessions.error)}</Text>
          <Button
            size="xs"
            variant="default"
            loading={sessions.isFetching}
            onClick={() => {
              void sessions.refetch();
              void progress.refetch();
            }}
          >
            Try again
          </Button>
        </Stack>
      </Alert>
    ) : (
      <Group justify="center" gap="sm" py="xl" role="status">
        <Loader size="sm" />
        <Text c="dimmed">Loading your sessions...</Text>
      </Group>
    );
  } else if (sessions.data.length === 0) {
    content = (
      <EmptyState
        size="sm"
        py="xl"
        title="No sessions yet"
        description="Upload a video of an exercise in your plan, and its result will show up here."
      >
        <EmptyState.Actions>
          <Button component={Link} to="/patient" color="teal" size="sm">
            Go to My Plan
          </Button>
        </EmptyState.Actions>
      </EmptyState>
    );
  } else {
    content = (
      <Stack gap="sm">
        {progress.error && !progress.data && (
          // The list loaded without its numbers. Each result page still has them.
          <Text size="sm" c="dimmed">
            Your scores could not load. Open a session to see its result.
          </Text>
        )}
        {sessions.data.map((session) => (
          <SessionCard
            key={session.id}
            session={session}
            point={points.get(session.id)}
            patientId={patientId}
          />
        ))}
      </Stack>
    );
  }

  return (
    <Container size="md" py="lg">
      <Paper withBorder p="lg" radius="md">
        <Title order={1} size="h2" mb="xs">
          Results & History
        </Title>
        <Text c="dimmed" mb="md">
          Every video you uploaded, newest first. Open one to see its result and feedback.
        </Text>
        {content}
      </Paper>
    </Container>
  );
}

/**
 * One session in the list, as a link to its result page: the exercise, when the video
 * was uploaded, its status, and for a complete session its count and form score.
 *
 * A session still processing polls its status (useSessionStatus), so its badge changes
 * as soon as the analysis has finished. The list and the scores then load again, which
 * brings the numbers.
 */
function SessionCard({
  session,
  point,
  patientId,
}: {
  session: SessionSummary;
  point: ProgressPoint | undefined;
  patientId: string;
}) {
  const queryClient = useQueryClient();
  const live = useSessionStatus(session.status === 'processing' ? session.id : undefined);
  const status = live.status ?? session.status;

  useEffect(() => {
    if (!live.isDone) return;
    void queryClient.invalidateQueries({ queryKey: getListPatientSessionsQueryKey(patientId) });
    void queryClient.invalidateQueries({ queryKey: getGetPatientProgressQueryKey(patientId) });
  }, [live.isDone, patientId, queryClient]);

  const badge = STATUS_BADGE[status];
  return (
    <Card
      component={Link}
      to={resultPath(session.id)}
      withBorder
      radius="md"
      padding="md"
      data-testid={`session-${session.id}`}
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap" gap="sm">
        <div>
          <Text fw={600}>{session.exercise_display_name}</Text>
          <Text size="sm" c="dimmed" component="time" dateTime={session.created_at}>
            {formatDateTime(session.created_at)}
          </Text>
        </div>
        <Group gap="xs" wrap="nowrap">
          <Badge color={badge.color} variant="light">
            {badge.label}
          </Badge>
          <Text c="dimmed" aria-hidden="true">
            ›
          </Text>
        </Group>
      </Group>
      <SessionSummaryLine status={status} point={point} />
    </Card>
  );
}

/** The line under a session's name: its numbers, or what is happening to it. */
function SessionSummaryLine({
  status,
  point,
}: {
  status: SessionSummary['status'];
  point: ProgressPoint | undefined;
}) {
  if (status === 'processing') {
    return (
      <Text size="sm" c="dimmed" mt="xs">
        Analyzing your video...
      </Text>
    );
  }
  if (status === 'failed') {
    return (
      <Text size="sm" c="red.8" mt="xs">
        We couldn't analyze this video. Open it to see why.
      </Text>
    );
  }
  // Complete. Without its point (the scores are loading, or could not load), the result
  // page still has the numbers.
  if (!point) return null;
  return (
    <Group gap="xs" mt="xs">
      <Text size="sm" fw={500}>
        {describeCount(point)}
      </Text>
      {/* null when no rep or hold was seen, which is not a score of 0. */}
      {point.form_score !== null && (
        <>
          <Text size="sm" c="dimmed">
            Form score
          </Text>
          <ScoreBadge score={point.form_score} />
        </>
      )}
    </Group>
  );
}

/** A form score, colored by band like the scores in ResultView. */
function ScoreBadge({ score }: { score: number }) {
  const band = getScoreBand(score);
  return (
    <Badge color={BAND_COLOR[band]} data-band={band} data-testid="session-score">
      {score} · {BAND_LABEL[band]}
    </Badge>
  );
}
