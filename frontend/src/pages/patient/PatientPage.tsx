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
  Modal,
} from '@mantine/core';

import { useGetMyPlan } from '@/api/plans';
import AccessibilityToolbar, { type TextScale } from './AccessibilityToolbar';
import { EXERCISE_INFO } from './exerciseInfo';
import PlanStatus from './PlanStatus';
import { describeFrequency, describeTarget, uploadPath } from './planDisplay';

/**
 * The patient's home page, "My plan": the exercises their therapist assigned
 * (GET /plans/me), each with its targets and a button to upload a video for it.
 */
export default function PatientPage() {
  const location = useLocation();
  const uploadedSessionId = (location.state as { uploadedSessionId?: string } | null)
    ?.uploadedSessionId;

  const { data: plan, isPending, isFetching, error, refetch } = useGetMyPlan();
  const exercises = plan?.exercises ?? [];

  // The plan exercise whose details dialog is open, by id.
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [textScale, setTextScale] = useState<TextScale>('normal');
  const [highContrast, setHighContrast] = useState<boolean>(false);

  const expandedExercise = exercises.find((item) => item.id === expandedId);
  const expandedInfo = expandedExercise && EXERCISE_INFO[expandedExercise.exercise.name];

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
              {exercises.length > 0 && (
                <Text c={highContrast ? 'dark.8' : 'dimmed'} style={{ fontSize: scaleStyles.body }}>
                  Click on any exercise card to expand details. Each video you upload is one set, so
                  record one video for each set.
                </Text>
              )}
            </div>
          </Group>

          {exercises.length === 0 ? (
            // Loading, no plan yet (404), or an error.
            <PlanStatus
              isPending={isPending}
              isFetching={isFetching}
              error={error}
              onRetry={() => void refetch()}
            />
          ) : (
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
              {exercises.map((item) => {
                const name = item.exercise.display_name;
                const info = EXERCISE_INFO[item.exercise.name];

                return (
                  <Card
                    key={item.id}
                    shadow="sm"
                    padding="md"
                    radius="md"
                    withBorder
                    role="button"
                    tabIndex={0}
                    aria-haspopup="dialog"
                    aria-label={`View details for ${name}`}
                    onClick={() => setExpandedId(item.id)}
                    onKeyDown={(e) => {
                      // Only keys pressed on the card itself. Enter on the Record / Upload
                      // link inside it must open the upload page, not this dialog.
                      if (e.target !== e.currentTarget) return;
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setExpandedId(item.id);
                      }
                    }}
                    style={{
                      cursor: 'pointer',
                      transition: 'transform 150ms ease, box-shadow 150ms ease',
                      borderWidth: highContrast ? '2px' : '1px',
                      borderColor: highContrast ? '#000000' : undefined,
                      backgroundColor: highContrast ? '#ffffff' : undefined,
                    }}
                    data-testid={`exercise-card-${item.exercise.name}`}
                  >
                    {info && (
                      <Card.Section>
                        <Image
                          src={info.imageUrl}
                          height={160}
                          alt={`Illustration showing posture for ${name}`}
                          fit="contain"
                          p="xs"
                          bg="gray.0"
                        />
                      </Card.Section>
                    )}

                    <Stack gap="xs" mt="sm">
                      <Group justify="space-between" align="center">
                        <Title
                          order={3}
                          style={{
                            fontSize: scaleStyles.title,
                            color: highContrast ? '#000000' : undefined,
                          }}
                        >
                          {name}
                        </Title>
                        <Badge
                          color={highContrast ? 'dark' : 'teal'}
                          variant={highContrast ? 'filled' : 'light'}
                        >
                          {describeTarget(item)}
                        </Badge>
                      </Group>

                      <Text
                        fw={500}
                        style={{
                          fontSize: scaleStyles.body,
                          color: highContrast ? '#000000' : undefined,
                        }}
                      >
                        {describeFrequency(item.times_per_week)}
                      </Text>

                      {info && (
                        <Text
                          c={highContrast ? 'dark.9' : 'dimmed'}
                          style={{ fontSize: scaleStyles.desc }}
                          lineClamp={2}
                        >
                          {info.instructions}
                        </Text>
                      )}

                      <Group justify="space-between" mt="xs">
                        <Button
                          variant="subtle"
                          size="xs"
                          color={highContrast ? 'dark' : 'teal'}
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedId(item.id);
                          }}
                        >
                          Expand Card
                        </Button>
                        <Button
                          color="teal"
                          size="xs"
                          radius="md"
                          component={Link}
                          to={uploadPath(item.id)}
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
          )}
        </Paper>

        {/* Expanded Card Modal covering most of the page (~85% width) with backdrop greying */}
        {expandedExercise && (
          <Modal
            opened={!!expandedExercise}
            onClose={() => setExpandedId(null)}
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
                {expandedExercise.exercise.display_name}
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
                  Target: {describeTarget(expandedExercise)}
                </Badge>
                <Badge size="lg" color="blue" variant="outline">
                  {describeFrequency(expandedExercise.times_per_week)}
                </Badge>
              </Group>

              {expandedInfo && (
                <Paper withBorder p="md" radius="md" bg="gray.0">
                  <Image
                    src={expandedInfo.imageUrl}
                    height={260}
                    alt={`Detailed illustration of ${expandedExercise.exercise.display_name}`}
                    fit="contain"
                  />
                </Paper>
              )}

              <Paper withBorder p="md" radius="md">
                <Title order={4} mb="xs">
                  How to Do It
                </Title>
                {expandedInfo && (
                  <Text size="md" mb="xs">
                    {expandedInfo.instructions}
                  </Text>
                )}
                <Text size="sm" c="dimmed">
                  Each video you upload is one set. Record one video for each set.
                </Text>
              </Paper>

              <Group justify="space-between" mt="md">
                <Button variant="default" onClick={() => setExpandedId(null)}>
                  Close
                </Button>
                <Button
                  color="teal"
                  size="md"
                  component={Link}
                  to={uploadPath(expandedExercise.id)}
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
