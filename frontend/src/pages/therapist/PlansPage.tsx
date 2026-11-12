import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  Alert,
  Anchor,
  Container,
  Group,
  Loader,
  NavLink,
  Paper,
  Text,
  Title,
} from '@mantine/core';

import { useListLinkedPatients } from '@/api/patients';
import { describeApiError } from '@/utils/apiErrors';

/**
 * The Plan Builder page in the navigation (/therapist/plans): pick a linked patient to
 * open their plan builder at /therapist/patients/:patientId/plan, the same address the
 * patient list links to.
 */
export default function PlansPage() {
  const patients = useListLinkedPatients();

  let content: ReactNode;
  if (!patients.data) {
    // Not loaded yet. (After it has loaded, a failed refetch in the background keeps the list.)
    content = patients.error ? (
      <Alert color="red" title="Couldn't load your patients">
        {describeApiError(patients.error)}
      </Alert>
    ) : (
      <Group gap="sm">
        <Loader size="sm" />
        <Text c="dimmed">Loading your patients…</Text>
      </Group>
    );
  } else if (patients.data.length === 0) {
    content = (
      <Text>
        You have no linked patients yet. Link a patient on the{' '}
        <Anchor component={Link} to="/therapist">
          Patients
        </Anchor>{' '}
        page first.
      </Text>
    );
  } else {
    content = patients.data.map((patient) => (
      <NavLink
        key={patient.id}
        component={Link}
        to={`/therapist/patients/${patient.id}/plan`}
        label={patient.email}
        rightSection={<span aria-hidden="true">›</span>}
        // Shows the whole email, even a long one: it may break anywhere instead of being
        // cut short, so two similar emails can still be told apart.
        styles={{ label: { overflowWrap: 'anywhere' } }}
      />
    ));
  }

  return (
    <Container size="md" py="md">
      <Paper withBorder p="lg" radius="md">
        <Title order={2} size="h3" mb="xs">
          Plan Builder
        </Title>
        <Text c="dimmed" mb="md">
          Choose a patient to build or change their exercise plan.
        </Text>
        {content}
      </Paper>
    </Container>
  );
}
