import { useState } from 'react';
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
  Image,
  RingProgress,
  Modal,
  Box,
} from '@mantine/core';

import { MOCK_ASSIGNED_EXERCISES, type AssignedExercise } from './mockExercises';
import AccessibilityToolbar, { type TextScale } from './AccessibilityToolbar';

export default function PatientPage() {
  const location = useLocation();
  const uploadedSessionId = (location.state as { uploadedSessionId?: string } | null)
    ?.uploadedSessionId;

  const [expandedExercise, setExpandedExercise] = useState<AssignedExercise | null>(null);
  const [textScale, setTextScale] = useState<TextScale>('normal');
  const [highContrast, setHighContrast] = useState<boolean>(false);

  // Font size multipliers based on accessibility textScale
  const scaleStyles = {
    normal: { title: '1.25rem', body: '0.875rem', desc: '0.8125rem' },
    large: { title: '1.45rem', body: '1rem', desc: '0.9375rem' },
    xlarge: { title: '1.65rem', body: '1.15rem', desc: '1.05rem' },
  }[textScale];

  return (
    <Container size="lg" py="md">
      <Stack gap="lg">
        {/* Accessibility Toolbar */}
        <AccessibilityToolbar
          textScale={textScale}
          onTextScaleChange={setTextScale}
          highContrast={highContrast}
          onHighContrastChange={setHighContrast}
        />

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

        <Paper
          withBorder
          p="lg"
          radius="md"
          style={{
            backgroundColor: highContrast ? '#ffffff' : undefined,
            borderColor: highContrast ? '#000000' : undefined,
            borderWidth: highContrast ? '2px' : '1px',
          }}
        >
          <Group justify="space-between" align="flex-start" mb="md">
            <div>
              <Title
                order={1}
                size="h2"
                style={{ fontSize: scaleStyles.title }}
                c={highContrast ? '#000000' : 'teal.8'}
              >
                My Exercise Plan
              </Title>
              <Text c={highContrast ? 'dark.8' : 'dimmed'} style={{ fontSize: scaleStyles.body }}>
                Click on any exercise card to expand details. Complete your assigned sets to reach
                your therapy goals.
              </Text>
            </div>
          </Group>

          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
            {MOCK_ASSIGNED_EXERCISES.map((exercise) => {
              const progressColor =
                exercise.progressPercent === 100
                  ? 'teal'
                  : exercise.progressPercent > 0
                    ? 'blue'
                    : 'gray';

              return (
                <Card
                  key={exercise.id}
                  shadow="sm"
                  padding="md"
                  radius="md"
                  withBorder
                  role="button"
                  tabIndex={0}
                  aria-haspopup="dialog"
                  aria-label={`View details for ${exercise.displayName}. Progress: ${exercise.progressPercent} percent.`}
                  onClick={() => setExpandedExercise(exercise)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setExpandedExercise(exercise);
                    }
                  }}
                  style={{
                    cursor: 'pointer',
                    transition: 'transform 150ms ease, box-shadow 150ms ease',
                    borderWidth: highContrast ? '2px' : '1px',
                    borderColor: highContrast ? '#000000' : undefined,
                    backgroundColor: highContrast ? '#ffffff' : undefined,
                  }}
                  data-testid={`exercise-card-${exercise.name}`}
                >
                  <Card.Section>
                    <Image
                      src={exercise.imageUrl}
                      height={160}
                      alt={`Illustration showing posture for ${exercise.displayName}`}
                      fit="contain"
                      p="xs"
                      bg="gray.0"
                    />
                  </Card.Section>

                  <Stack gap="xs" mt="sm">
                    <Group justify="space-between" align="center">
                      <Title
                        order={3}
                        style={{
                          fontSize: scaleStyles.title,
                          color: highContrast ? '#000000' : undefined,
                        }}
                      >
                        {exercise.displayName}
                      </Title>
                      <Badge
                        color={highContrast ? 'dark' : 'teal'}
                        variant={highContrast ? 'filled' : 'light'}
                      >
                        {exercise.targetDescription}
                      </Badge>
                    </Group>

                    {/* Progress representation: Pie chart (RingProgress) + Written Description */}
                    <Paper
                      withBorder
                      p="xs"
                      radius="sm"
                      bg={highContrast ? '#f8f9fa' : 'gray.0'}
                      style={{
                        borderColor: highContrast ? '#000000' : undefined,
                      }}
                    >
                      <Group gap="md" align="center" wrap="nowrap">
                        <RingProgress
                          size={85}
                          thickness={9}
                          roundCaps
                          sections={[{ value: exercise.progressPercent, color: progressColor }]}
                          label={
                            <Text
                              ta="center"
                              fw={700}
                              size="xs"
                              c={highContrast ? '#000000' : undefined}
                            >
                              {exercise.progressPercent}%
                            </Text>
                          }
                          aria-label={`${exercise.displayName} progress pie chart: ${exercise.progressPercent}% complete`}
                        />
                        <Box style={{ flex: 1 }}>
                          <Text
                            size="xs"
                            fw={700}
                            tt="uppercase"
                            c={highContrast ? '#000000' : 'dimmed'}
                          >
                            Today's Progress
                          </Text>
                          <Text
                            style={{
                              fontSize: scaleStyles.desc,
                              lineHeight: 1.35,
                              color: highContrast ? '#000000' : undefined,
                            }}
                          >
                            {exercise.progressDescription}
                          </Text>
                        </Box>
                      </Group>
                    </Paper>

                    <Text
                      c={highContrast ? 'dark.9' : 'dimmed'}
                      style={{ fontSize: scaleStyles.desc }}
                      lineClamp={2}
                    >
                      {exercise.instructions}
                    </Text>

                    <Group justify="space-between" mt="xs">
                      <Button
                        variant="subtle"
                        size="xs"
                        color={highContrast ? 'dark' : 'teal'}
                        onClick={(e) => {
                          e.stopPropagation();
                          setExpandedExercise(exercise);
                        }}
                      >
                        Expand Card
                      </Button>
                      <Button
                        color="teal"
                        size="xs"
                        radius="md"
                        component={Link}
                        to={`/patient/upload?plan_exercise_id=${exercise.id}&exercise=${exercise.name}`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        Record / Upload
                      </Button>
                    </Group>
                  </Stack>
                </Card>
              );
            })}
          </SimpleGrid>
        </Paper>

        {/* Expanded Card Modal covering most of the page (~85% width) with backdrop greying */}
        {expandedExercise && (
          <Modal
            opened={!!expandedExercise}
            onClose={() => setExpandedExercise(null)}
            transitionProps={{ duration: 0 }}
            size="85%"
            radius="md"
            centered
            title={
              <Text
                fw={700}
                style={{
                  fontSize: scaleStyles.title,
                  color: highContrast ? '#000000' : 'teal.8',
                }}
              >
                {expandedExercise.displayName}
              </Text>
            }
            overlayProps={{
              backgroundOpacity: 0.65,
              blur: 4,
            }}
            styles={{
              content: {
                borderWidth: highContrast ? '2px' : '1px',
                borderColor: highContrast ? '#000000' : undefined,
              },
            }}
            data-testid="expanded-exercise-modal"
          >
            <Stack gap="lg" p="md">
              <Group justify="space-between" align="center" wrap="wrap">
                <Badge
                  size="lg"
                  color={highContrast ? 'dark' : 'teal'}
                  variant={highContrast ? 'filled' : 'light'}
                >
                  Target: {expandedExercise.targetDescription}
                </Badge>
                <Badge size="lg" color="blue" variant="outline">
                  Status: {expandedExercise.progressPercent}% Completed
                </Badge>
              </Group>

              <Paper withBorder p="md" radius="md" bg="gray.0">
                <Image
                  src={expandedExercise.imageUrl}
                  height={260}
                  alt={`Detailed illustration of ${expandedExercise.displayName}`}
                  fit="contain"
                />
              </Paper>

              {/* Expanded progress section */}
              <Paper withBorder p="md" radius="md">
                <Group gap="xl" align="center" wrap="wrap">
                  <RingProgress
                    size={130}
                    thickness={14}
                    roundCaps
                    sections={[
                      {
                        value: expandedExercise.progressPercent,
                        color:
                          expandedExercise.progressPercent === 100
                            ? 'teal'
                            : expandedExercise.progressPercent > 0
                              ? 'blue'
                              : 'gray',
                      },
                    ]}
                    label={
                      <Text ta="center" fw={700} size="md">
                        {expandedExercise.progressPercent}%
                      </Text>
                    }
                  />
                  <Box style={{ flex: 1 }}>
                    <Title order={4} mb="xs">
                      Daily Progress Summary
                    </Title>
                    <Text size="md" mb="xs">
                      {expandedExercise.progressDescription}
                    </Text>
                    <Text size="sm" c="dimmed">
                      {expandedExercise.instructions}
                    </Text>
                  </Box>
                </Group>
              </Paper>

              <Group justify="space-between" mt="md">
                <Button variant="default" onClick={() => setExpandedExercise(null)}>
                  Close
                </Button>
                <Button
                  color="teal"
                  size="md"
                  component={Link}
                  to={`/patient/upload?plan_exercise_id=${expandedExercise.id}&exercise=${expandedExercise.name}`}
                >
                  Record / Upload Set
                </Button>
              </Group>
            </Stack>
          </Modal>
        )}
      </Stack>
    </Container>
  );
}
