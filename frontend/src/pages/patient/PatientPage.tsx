import {
  Container,
  Title,
  Text,
  Button,
  Card,
  Group,
  Badge,
  Stack,
  SimpleGrid,
  Paper,
  Box,
} from '@mantine/core';
import { Link } from 'react-router-dom';

export default function PatientPage() {
  return (
    <Container size="lg" py="xl">
      <Group justify="space-between" mb="xl">
        <Box>
          <Title order={1} c="teal.8">
            PTAssist
          </Title>
          <Text c="dimmed" size="sm">
            Patient Portal
          </Text>
        </Box>
        {/* TODO: SCRUM-34 - replace placeholder button with role routing */}
        <Button component={Link} to="/therapist" variant="light" color="teal" size="sm">
          Switch to Therapist View
        </Button>
      </Group>

      <Stack gap="lg">
        <Paper withBorder p="lg" radius="md">
          <Title order={2} size="h3" mb="xs">
            My Exercise Plan
          </Title>
          <Text c="dimmed" mb="md">
            Complete your assigned exercises and upload your session videos for AI-augmented
            feedback.
          </Text>

          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
            <Card shadow="sm" padding="lg" radius="md" withBorder>
              <Group justify="space-between" mb="xs">
                <Text fw={500}>Squat</Text>
                <Badge color="teal">3 sets x 10 reps</Badge>
              </Group>
              <Text size="sm" c="dimmed" mb="md">
                Keep your back straight and knees behind your toes.
              </Text>
              <Button color="teal" fullWidth radius="md">
                Record / Upload
              </Button>
            </Card>

            <Card shadow="sm" padding="lg" radius="md" withBorder>
              <Group justify="space-between" mb="xs">
                <Text fw={500}>Shoulder Abduction</Text>
                <Badge color="teal">3 sets x 8 reps</Badge>
              </Group>
              <Text size="sm" c="dimmed" mb="md">
                Raise your arm laterally up to shoulder height.
              </Text>
              <Button color="teal" fullWidth radius="md">
                Record / Upload
              </Button>
            </Card>

            <Card shadow="sm" padding="lg" radius="md" withBorder>
              <Group justify="space-between" mb="xs">
                <Text fw={500}>Lunge</Text>
                <Badge color="gray">Upcoming</Badge>
              </Group>
              <Text size="sm" c="dimmed" mb="md">
                Step forward with your left foot, maintaining upright posture.
              </Text>
              <Button color="gray" variant="light" fullWidth radius="md">
                View Details
              </Button>
            </Card>
          </SimpleGrid>
        </Paper>

        <Paper withBorder p="lg" radius="md">
          <Title order={2} size="h3" mb="xs">
            Recent Results & Feedback
          </Title>
          <Text c="dimmed">
            No completed sessions recorded yet. Upload a video to see rep counts and form analysis.
          </Text>
        </Paper>
      </Stack>
    </Container>
  );
}
