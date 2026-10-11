import {
  Container,
  Title,
  Text,
  Button,
  Group,
  Stack,
  Paper,
  Table,
  Badge,
  Box,
} from '@mantine/core';
import { Link } from 'react-router-dom';

const mockPatients = [
  { id: '1', name: 'Alex Johnson', plan: 'Post-Op Knee Rehab', sessions: 12, compliance: '92%' },
  { id: '2', name: 'Maria Garcia', plan: 'Rotator Cuff Protocol', sessions: 8, compliance: '85%' },
  { id: '3', name: 'Sam Taylor', plan: 'Lumbar Spine Stability', sessions: 15, compliance: '98%' },
];

export default function TherapistPage() {
  return (
    <Container size="lg" py="xl">
      <Group justify="space-between" mb="xl">
        <Box>
          <Title order={1} c="teal.8">
            PTAssist
          </Title>
          <Text c="dimmed" size="sm">
            Therapist Dashboard
          </Text>
        </Box>
        <Group>
          <Button variant="filled" color="teal" size="sm">
            + Link New Patient
          </Button>
          <Button component={Link} to="/patient" variant="light" color="teal" size="sm">
            Switch to Patient View
          </Button>
        </Group>
      </Group>

      <Stack gap="lg">
        <Paper withBorder p="lg" radius="md">
          <Group justify="space-between" mb="md">
            <div>
              <Title order={2} size="h3">
                Assigned Patients
              </Title>
              <Text c="dimmed" size="sm">
                Monitor home exercise completion and form analysis results.
              </Text>
            </div>
          </Group>

          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Patient Name</Table.Th>
                <Table.Th>Active Plan</Table.Th>
                <Table.Th>Total Sessions</Table.Th>
                <Table.Th>Compliance</Table.Th>
                <Table.Th>Action</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {mockPatients.map((patient) => (
                <Table.Tr key={patient.id}>
                  <Table.Td fw={500}>{patient.name}</Table.Td>
                  <Table.Td>{patient.plan}</Table.Td>
                  <Table.Td>{patient.sessions}</Table.Td>
                  <Table.Td>
                    <Badge color="teal" variant="light">
                      {patient.compliance}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Button size="xs" variant="outline" color="teal">
                      View Progress
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>

        <Paper withBorder p="lg" radius="md">
          <Title order={2} size="h3" mb="xs">
            Plan Builder
          </Title>
          <Text c="dimmed" mb="md">
            Assign custom exercises, rep targets, and frequency to linked patients.
          </Text>
          <Button variant="default">Create New Plan Template</Button>
        </Paper>
      </Stack>
    </Container>
  );
}

