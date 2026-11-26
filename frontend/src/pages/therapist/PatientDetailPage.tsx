import { Link, useParams } from 'react-router-dom';
import {
  Anchor,
  Button,
  Container,
  EmptyState,
  Group,
  Paper,
  Stack,
  Table,
  Text,
  Title,
  VisuallyHidden,
} from '@mantine/core';

import type { SessionSummary } from '@/api/model';
import { useListLinkedPatients } from '@/api/patients';
import { useListPatientSessions } from '@/api/results';
import SessionStatusBadge from '@/components/SessionStatusBadge';
import { POLL_INTERVAL_MS } from '@/hooks/useSessionStatus';
import { LoadErrorAlert, LoadingMessage, PatientNotFound } from './PageStates';
import { formatDate, formatDateTime, isAccessDenied, sessionPath } from './sessionDisplay';

/**
 * A linked patient's detail page (/therapist/patients/:patientId): who the patient is,
 * and every session they uploaded, newest first, with its exercise, upload time, and
 * status. Each session opens its result at
 * /therapist/patients/:patientId/sessions/:sessionId (SessionResultPage).
 *
 * The API decides what the therapist may see (backend/README.md, Sessions, results, and
 * progress): only linked users who are still patients. It answers 404 for anyone else.
 */
export default function PatientDetailPage() {
  const { patientId = '' } = useParams();
  const patients = useListLinkedPatients();
  const patient = patients.data?.find((linked) => linked.id === patientId);
  // Asks for the sessions only once the patient is known to be linked, so an address with
  // an unknown id sends no request.
  const sessions = useListPatientSessions(patientId, {
    query: {
      enabled: patient !== undefined,
      // While a session is processing, asks again every few seconds, so its status changes
      // by itself when the analysis finishes. Stops after an error, as useSessionStatus does.
      refetchInterval: (query) =>
        query.state.status !== 'error' &&
        query.state.data?.some((session) => session.status === 'processing')
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
          <LoadingMessage>Loading the patient…</LoadingMessage>
        )}
      </Container>
    );
  }
  // Checked before any session is shown, even one from the cache: an id that isn't one of
  // the therapist's patients, or a patient whose sessions the API no longer shows them
  // (unlinked, or no longer a patient).
  if (!patient || isAccessDenied(sessions.error)) {
    return (
      <Container size="md" py="md">
        <PatientNotFound />
      </Container>
    );
  }

  return (
    <Container size="md" py="md">
      <Stack gap="lg">
        <div>
          <Anchor component={Link} to="/therapist" size="sm">
            Back to your patients
          </Anchor>
          <Group justify="space-between" align="flex-start" wrap="nowrap" mt="xs">
            <div style={{ minWidth: 0 }}>
              {/* Long emails have no spaces to wrap at, so they may break anywhere. */}
              <Title order={2} size="h3" style={{ overflowWrap: 'anywhere' }}>
                {patient.email}
              </Title>
              <Text c="dimmed" size="sm">
                Linked on <time dateTime={patient.linked_at}>{formatDate(patient.linked_at)}</time>
              </Text>
            </div>
            {/* The plan builder (SCRUM-76) for this patient. */}
            <Button
              component={Link}
              to={`/therapist/patients/${patient.id}/plan`}
              size="xs"
              variant="light"
              color="teal"
              aria-label={`Plan for ${patient.email}`}
            >
              Plan
            </Button>
          </Group>
        </div>

        <Paper withBorder p="lg" radius="md">
          <Title order={3} size="h4">
            Sessions
          </Title>
          <Text c="dimmed" size="sm" mb="md">
            Every video the patient uploaded, newest first. Open one to see its result.
          </Text>
          <SessionList
            patientId={patient.id}
            sessions={sessions.data}
            error={sessions.error}
            retrying={sessions.isFetching}
            onRetry={() => void sessions.refetch()}
          />
        </Paper>
      </Stack>
    </Container>
  );
}

/** The patient's sessions (GET /patients/{patient_id}/sessions), or why they aren't shown. */
function SessionList({
  patientId,
  sessions,
  error,
  retrying,
  onRetry,
}: {
  patientId: string;
  sessions: SessionSummary[] | undefined;
  error: Error | null;
  retrying: boolean;
  onRetry: () => void;
}) {
  // Until the first answer. A later refresh keeps the last list on screen.
  if (!sessions) {
    return error ? (
      <LoadErrorAlert
        title="Couldn't load the sessions"
        error={error}
        retrying={retrying}
        onRetry={onRetry}
      />
    ) : (
      <LoadingMessage>Loading the sessions…</LoadingMessage>
    );
  }

  if (!sessions.length) {
    return (
      <EmptyState
        size="sm"
        py="xl"
        title="No sessions yet"
        description="Each video the patient uploads for an exercise of their plan shows here, with its result."
      />
    );
  }

  return (
    <Table.ScrollContainer minWidth={480}>
      <Table highlightOnHover verticalSpacing="sm">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Exercise</Table.Th>
            <Table.Th>Uploaded</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>
              <VisuallyHidden>Result</VisuallyHidden>
            </Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {sessions.map((session) => {
            const uploaded = formatDateTime(session.created_at);
            return (
              <Table.Tr key={session.id}>
                <Table.Td fw={500}>{session.exercise_display_name}</Table.Td>
                <Table.Td>
                  <Text size="sm" component="time" dateTime={session.created_at}>
                    {uploaded}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <SessionStatusBadge status={session.status} />
                </Table.Td>
                <Table.Td>
                  <Group justify="flex-end">
                    <Button
                      component={Link}
                      to={sessionPath(patientId, session.id)}
                      size="xs"
                      variant="light"
                      color="teal"
                      aria-label={`Open the ${session.exercise_display_name} session from ${uploaded}`}
                    >
                      Open
                    </Button>
                  </Group>
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
