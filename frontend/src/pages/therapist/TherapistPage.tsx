import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Alert,
  Badge,
  Button,
  Container,
  EmptyState,
  Group,
  Loader,
  Paper,
  Table,
  Text,
  Title,
  VisuallyHidden,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';

import type { LinkedPatientResponse, SessionStatus } from '@/api/model';
import { useListLinkedPatients } from '@/api/patients';
import { useListPatientSessions } from '@/api/results';
import { apiErrorText } from './apiErrorText';
import LinkPatientModal from './LinkPatientModal';
import UnlinkPatientModal from './UnlinkPatientModal';

/** How each session status shows in the list. */
const STATUS_BADGE: Record<SessionStatus, { label: string; color: string }> = {
  complete: { label: 'Complete', color: 'teal' },
  processing: { label: 'Processing', color: 'yellow' },
  failed: { label: 'Failed', color: 'red' },
};

/**
 * The therapist's home page: their linked patients, each with their last session, and
 * buttons to link a patient by email, open a patient's plan, or unlink a patient.
 */
export default function TherapistPage() {
  const [linkOpened, linkDialog] = useDisclosure(false);
  // The patient the unlink dialog asks about, while it is open.
  const [unlinkTarget, setUnlinkTarget] = useState<LinkedPatientResponse | null>(null);
  // A short confirmation after a link or an unlink.
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <Container size="lg" py="md">
      <Paper withBorder p="lg" radius="md">
        <Group justify="space-between" mb="md">
          <div>
            <Title order={1} size="h3">
              Assigned Patients
            </Title>
            <Text c="dimmed" size="sm">
              Patients you linked by email, with their last session.
            </Text>
          </div>
          <Button color="teal" size="sm" onClick={linkDialog.open}>
            + Link New Patient
          </Button>
        </Group>

        {notice && (
          <Alert
            color="teal"
            mb="md"
            withCloseButton
            closeButtonLabel="Dismiss"
            onClose={() => setNotice(null)}
          >
            {notice}
          </Alert>
        )}

        <PatientList onUnlink={setUnlinkTarget} />
      </Paper>

      <LinkPatientModal
        opened={linkOpened}
        onClose={linkDialog.close}
        onLinked={(patient) => {
          linkDialog.close();
          setNotice(`Linked ${patient.email}.`);
        }}
      />
      <UnlinkPatientModal
        patient={unlinkTarget}
        onClose={() => setUnlinkTarget(null)}
        onUnlinked={(patient) => {
          setUnlinkTarget(null);
          setNotice(`Unlinked ${patient.email}.`);
        }}
      />
    </Container>
  );
}

/** The caller's linked patients (GET /therapist/patients), or why they aren't shown. */
function PatientList({ onUnlink }: { onUnlink: (patient: LinkedPatientResponse) => void }) {
  const { data: patients, error } = useListLinkedPatients();

  // Until the first answer. A later refresh keeps the last list on screen.
  if (!patients) {
    return error ? (
      <Alert color="red" title="Could not load your patients">
        {apiErrorText(error)}
      </Alert>
    ) : (
      <Group justify="center" gap="xs" py="xl">
        <Loader size="sm" />
        <Text c="dimmed" size="sm">
          Loading your patients…
        </Text>
      </Group>
    );
  }

  if (!patients.length) {
    return (
      <EmptyState
        size="sm"
        py="xl"
        title="No linked patients yet"
        description="Link a patient with the email they signed in to PTAssist with."
      />
    );
  }

  return (
    <Table.ScrollContainer minWidth={560}>
      <Table highlightOnHover verticalSpacing="sm">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Patient</Table.Th>
            <Table.Th>Last session</Table.Th>
            <Table.Th>
              <VisuallyHidden>Actions</VisuallyHidden>
            </Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {patients.map((patient) => (
            <Table.Tr key={patient.id}>
              <Table.Td fw={500}>{patient.email}</Table.Td>
              <Table.Td>
                <LastSession patientId={patient.id} />
              </Table.Td>
              <Table.Td>
                <Group gap="xs" justify="flex-end" wrap="nowrap">
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
                  <Button
                    size="xs"
                    variant="subtle"
                    color="red"
                    aria-label={`Unlink ${patient.email}`}
                    onClick={() => onUnlink(patient)}
                  >
                    Unlink
                  </Button>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

/**
 * The patient's newest session: its status, exercise, and upload time.
 *
 * Each row asks for its own patient's sessions, so a list of N patients makes N more
 * requests (N+1), and each answer has all of that patient's sessions, not just the
 * newest. That is fine for a proof of concept with a few patients. With many, the API
 * should send each patient's last session with GET /therapist/patients instead.
 */
function LastSession({ patientId }: { patientId: string }) {
  const { data: sessions, error } = useListPatientSessions(patientId);

  if (!sessions) {
    return (
      <Text size="sm" c={error ? 'red' : 'dimmed'}>
        {error ? "Couldn't load sessions" : 'Loading…'}
      </Text>
    );
  }

  // The API lists sessions newest first.
  const last = sessions[0];
  if (!last) {
    return (
      <Text size="sm" c="dimmed">
        No sessions yet
      </Text>
    );
  }

  const badge = STATUS_BADGE[last.status];
  return (
    <Group gap="xs">
      <Badge color={badge.color} variant="light">
        {badge.label}
      </Badge>
      <Text size="sm">{last.exercise_display_name}</Text>
      <Text size="sm" c="dimmed" component="time" dateTime={last.created_at}>
        {formatDateTime(last.created_at)}
      </Text>
    </Group>
  );
}

/** A date and time in the browser's language, for example "Nov 10, 2026, 3:00 PM". */
function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}
