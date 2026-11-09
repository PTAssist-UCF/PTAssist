import { Link, useLocation } from 'react-router-dom';
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
  Alert,
} from '@mantine/core';

export default function PatientPage() {
  const location = useLocation();
  const uploadedSessionId = (location.state as { uploadedSessionId?: string } | null)
    ?.uploadedSessionId;

  return (
    <Container size="lg" py="md">
      <Stack gap="lg">
        {uploadedSessionId && (
          <Alert color="teal" title="Upload in Progress">
            <Group gap="xs" mb="xs">
              <Text size="sm">
                Session{' '}
                <Text span fw={600}>
                  {uploadedSessionId}
                </Text>{' '}
                was successfully uploaded and is currently
              </Text>
              <Badge color="yellow" variant="light">
                processing
              </Badge>
            </Group>
            <Text size="sm">Your feedback and scores will appear once analysis is complete.</Text>
          </Alert>
        )}

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
              <Button
                color="teal"
                fullWidth
                radius="md"
                component={Link}
                to="/patient/upload?exercise=squat"
              >
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
              <Button
                color="teal"
                fullWidth
                radius="md"
                component={Link}
                to="/patient/upload?exercise=shoulder_abduction"
              >
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
