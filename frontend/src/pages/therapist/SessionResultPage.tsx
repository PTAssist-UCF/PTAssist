import type { ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Alert,
  Anchor,
  Code,
  Container,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  Title,
} from '@mantine/core';

import type { SessionResultResponse, SessionSummary } from '@/api/model';
import { useListLinkedPatients } from '@/api/patients';
import { useGetSessionResult, useListPatientSessions } from '@/api/results';
import { ResultView } from '@/components/ResultView/ResultView';
import SessionStatusBadge from '@/components/SessionStatusBadge';
import { POLL_INTERVAL_MS } from '@/hooks/useSessionStatus';
import { LoadErrorAlert, LoadingMessage, NotFoundAlert, PatientNotFound } from './PageStates';
import { formatDateTime, isAccessDenied, isStubResult, patientPath } from './sessionDisplay';

/**
 * One of a linked patient's sessions, for the therapist
 * (/therapist/patients/:patientId/sessions/:sessionId): its exercise, upload time, and
 * status, and its result from GET /sessions/{session_id}/result in the result view
 * (ResultView, SCRUM-59). While the session is processing, the page says so and asks
 * again every few seconds until the result is there.
 *
 * Opened from the patient's detail page (PatientDetailPage), which lists their sessions.
 */
export default function SessionResultPage() {
  const { patientId = '', sessionId = '' } = useParams();
  const patients = useListLinkedPatients();
  const patient = patients.data?.find((linked) => linked.id === patientId);
  // Asks for the sessions only once the patient is known to be linked.
  const sessions = useListPatientSessions(patientId, {
    query: { enabled: patient !== undefined },
  });
  // The session as the patient's list has it. Its result is asked for only once the
  // session is in this patient's list: the API would also show another linked patient's
  // session, which would then appear under this patient's name. So an address with one,
  // or with an id that doesn't exist, sends no request for a result.
  const summary = sessions.data?.find((item) => item.id === sessionId);
  const result = useGetSessionResult(sessionId, {
    query: {
      enabled: summary !== undefined,
      // While the session is processing, asks again every few seconds. The page needs no
      // time limit: the result route fails a session stuck in processing (SCRUM-66), so
      // the answer ends as failed. Stops after an error, as useSessionStatus does.
      refetchInterval: (query) =>
        query.state.status !== 'error' && query.state.data?.status === 'processing'
          ? POLL_INTERVAL_MS
          : false,
    },
  });

  // Until the first answer. After that, a failed refetch in the background keeps the page.
  if (!patients.data) {
    return (
      <Container size="md" py="md">
        {patients.error ? (
          <LoadErrorAlert
            title="Couldn't load your patients"
            error={patients.error}
            retrying={patients.isFetching}
            onRetry={() => void patients.refetch()}
          />
        ) : (
          <LoadingMessage>Loading the session…</LoadingMessage>
        )}
      </Container>
    );
  }
  // Checked before anything is shown, even from the cache, as on the patient's page.
  if (!patient || isAccessDenied(sessions.error)) {
    return (
      <Container size="md" py="md">
        <PatientNotFound />
      </Container>
    );
  }

  let content: ReactNode;
  if (!summary) {
    // Not in the patient's list, or not yet: a list that is loading again may have it,
    // for example a session the patient uploaded since the list was last read.
    if (sessions.isPending || sessions.isFetching) {
      content = <LoadingMessage>Loading the session…</LoadingMessage>;
    } else if (sessions.error) {
      content = (
        <LoadErrorAlert
          title="Couldn't load the sessions"
          error={sessions.error}
          retrying={false}
          onRetry={() => void sessions.refetch()}
        />
      );
    } else {
      content = <SessionNotFound patientId={patient.id} />;
    }
  } else if (isAccessDenied(result.error)) {
    // For example, the patient was unlinked since their list was read.
    content = <SessionNotFound patientId={patient.id} />;
  } else {
    content = (
      <>
        {/* The result's copy of the session is the newer one: it is polled. */}
        <SessionHeader session={result.data ?? summary} patientEmail={patient.email} />
        {result.data ? (
          <SessionOutcome
            session={result.data}
            checkError={result.error}
            retrying={result.isFetching}
            onRetry={() => void result.refetch()}
          />
        ) : result.error ? (
          <LoadErrorAlert
            title="Couldn't load the result"
            error={result.error}
            retrying={result.isFetching}
            onRetry={() => void result.refetch()}
          />
        ) : (
          <LoadingMessage>Loading the result…</LoadingMessage>
        )}
      </>
    );
  }

  return (
    <Container size="md" py="md">
      <Stack gap="lg">
        <div>
          <Anchor component={Link} to={patientPath(patient.id)} size="sm">
            Back to all sessions
          </Anchor>
        </div>
        {content}
      </Stack>
    </Container>
  );
}

/** Which session this is: its exercise and status, whose it is, and when it was uploaded. */
function SessionHeader({
  session,
  patientEmail,
}: {
  session: SessionSummary;
  patientEmail: string;
}) {
  return (
    <div>
      <Group gap="sm">
        <Title order={2} size="h3">
          {session.exercise_display_name}
        </Title>
        <SessionStatusBadge status={session.status} />
      </Group>
      {/* Long emails have no spaces to wrap at, so they may break anywhere. */}
      <Text c="dimmed" size="sm" style={{ overflowWrap: 'anywhere' }}>
        {patientEmail}, uploaded{' '}
        <time dateTime={session.created_at}>{formatDateTime(session.created_at)}</time>
      </Text>
    </div>
  );
}

/**
 * What came of the session: its result, or a note that it is still processing. The result
 * view shows the result in the same words as for the patient (they are written to the
 * patient), without the patient's "Upload again" button.
 */
function SessionOutcome({
  session,
  checkError,
  retrying,
  onRetry,
}: {
  session: SessionResultResponse;
  /** Why the last check for a newer answer failed, if it did. */
  checkError: Error | null;
  retrying: boolean;
  onRetry: () => void;
}) {
  const { result } = session;

  if (result === null) {
    // The API saves the result and the status together, so only a processing session has
    // no result. Anything else would be a bug: say so instead of waiting for it.
    if (session.status !== 'processing') {
      return (
        <Alert color="gray" title="No result">
          No result was saved for this session.
        </Alert>
      );
    }
    return (
      <Stack gap="sm">
        <Paper withBorder p="lg" radius="md" role="status">
          <Group gap="sm" wrap="nowrap">
            <Loader size="sm" />
            <div>
              <Text fw={600}>Still processing</Text>
              <Text size="sm" c="dimmed">
                The video is being analyzed. Its result shows here as soon as it&apos;s ready.
              </Text>
            </div>
          </Group>
        </Paper>
        {/* The page stopped asking after this error; Try again asks once more. */}
        {checkError && (
          <LoadErrorAlert
            title="Couldn't check for the result"
            error={checkError}
            retrying={retrying}
            onRetry={onRetry}
          />
        )}
      </Stack>
    );
  }

  return (
    <Stack gap="sm">
      {isStubResult(result) && (
        <Alert color="yellow" title="Placeholder result">
          PTAssist can&apos;t analyze this exercise yet, so this result is a made-up example, not
          taken from the patient&apos;s video.
        </Alert>
      )}
      <ResultView result={result} />
      {/* For a failure, the code says why (docs/analysis-result.md, Failures). The version
          tells results of different analysis code apart (Versions). A session the backend
          failed itself, such as one stuck in processing, has no version. */}
      {(result.error_code || result.analyzer_version) && (
        <Text size="xs" c="dimmed">
          {result.error_code && (
            <>
              Error code: <Code>{result.error_code}</Code>.{' '}
            </>
          )}
          {result.analyzer_version && `Analyzer version ${result.analyzer_version}.`}
        </Text>
      )}
    </Stack>
  );
}

/** The session isn't one of this patient's, doesn't exist, or the API won't show it. */
function SessionNotFound({ patientId }: { patientId: string }) {
  return (
    <NotFoundAlert
      title="Session not found"
      backTo={patientPath(patientId)}
      backLabel="See this patient's sessions"
    >
      This isn&apos;t one of this patient&apos;s sessions, or you can&apos;t see it.
    </NotFoundAlert>
  );
}
