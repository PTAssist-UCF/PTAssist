import { Group, Paper, Text, SegmentedControl, Switch } from '@mantine/core';

export type TextScale = 'normal' | 'large' | 'xlarge';

interface AccessibilityToolbarProps {
  textScale: TextScale;
  onTextScaleChange: (scale: TextScale) => void;
  highContrast: boolean;
  onHighContrastChange: (enabled: boolean) => void;
}

export default function AccessibilityToolbar({
  textScale,
  onTextScaleChange,
  highContrast,
  onHighContrastChange,
}: AccessibilityToolbarProps) {
  return (
    <Paper
      withBorder
      p="sm"
      radius="md"
      role="region"
      aria-label="Accessibility options"
      style={{
        backgroundColor: highContrast ? '#ffffff' : undefined,
        borderColor: highContrast ? '#000000' : undefined,
        borderWidth: highContrast ? '2px' : '1px',
      }}
    >
      <Group justify="space-between" wrap="wrap" gap="md">
        <Group gap="xs">
          <Text size="sm" fw={highContrast ? 700 : 600} c={highContrast ? 'dark.9' : undefined}>
            Text Size:
          </Text>
          <SegmentedControl
            size="xs"
            value={textScale}
            onChange={(val) => onTextScaleChange(val as TextScale)}
            aria-label="Adjust text scaling size"
            data={[
              { label: 'Normal', value: 'normal' },
              { label: 'Large (115%)', value: 'large' },
              { label: 'Extra Large (130%)', value: 'xlarge' },
            ]}
            color="teal"
          />
        </Group>

        <Group gap="sm">
          <Switch
            label="High Contrast"
            checked={highContrast}
            onChange={(e) => onHighContrastChange(e.currentTarget.checked)}
            color="teal"
            size="sm"
            aria-label="Toggle high contrast display mode"
            styles={{
              label: {
                fontWeight: highContrast ? 700 : 500,
                color: highContrast ? '#000000' : undefined,
              },
            }}
          />
        </Group>
      </Group>
    </Paper>
  );
}
