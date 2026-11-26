import { useId } from 'react';
import { List, Paper, Stack, Text, ThemeIcon, Title } from '@mantine/core';

import type { ExerciseResponse } from '@/api/model';
import { GENERAL_RECORDING_TIPS, getRecordingGuidance } from './recordingGuidance';

// The bullet of each tip. Hidden from screen readers, which already read out a list.
const bullet = (
  <ThemeIcon color="teal" size={20} radius="xl" aria-hidden="true">
    •
  </ThemeIcon>
);

/**
 * How to film this exercise (recordingGuidance.ts): where the phone goes, what must stay in
 * the frame, the start position, and how to move and finish, then the tips for every
 * exercise. An exercise without guidance of its own, such as one added to the library
 * later, gets only the tips for every exercise.
 */
export default function RecordingTips({ exercise }: { exercise: ExerciseResponse }) {
  const headingId = useId();
  const guidance = getRecordingGuidance(exercise.name);

  return (
    <Paper withBorder p="md" radius="md" role="region" aria-labelledby={headingId}>
      <Stack gap="md">
        <Title id={headingId} order={3} size="h4">
          Recording Tips for {exercise.display_name}
        </Title>

        {guidance && (
          <div>
            <Title order={4} size="h5" mb="xs">
              Set Up Your Phone
            </Title>
            <List spacing="xs" icon={bullet}>
              {[
                ['Which way to face', guidance.view],
                ['Phone', guidance.phone],
                ['Phone height', guidance.height],
                ['Distance', guidance.distance],
                ['Keep in the frame', guidance.framing],
              ].map(([label, text]) => (
                <List.Item key={label}>
                  <Text span inherit fw={600}>
                    {label}:
                  </Text>{' '}
                  {text}
                </List.Item>
              ))}
            </List>
          </div>
        )}

        <div>
          <Title order={4} size="h5" mb="xs">
            When You Record
          </Title>
          <List spacing="xs" icon={bullet}>
            {guidance && (
              <List.Item>
                <Text span inherit fw={600}>
                  Start position:
                </Text>{' '}
                {guidance.startPosition}
              </List.Item>
            )}
            {[...(guidance?.tips ?? []), ...GENERAL_RECORDING_TIPS].map((tip) => (
              <List.Item key={tip}>{tip}</List.Item>
            ))}
          </List>
        </div>
      </Stack>
    </Paper>
  );
}
