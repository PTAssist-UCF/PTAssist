import { Container, Paper, Text, Title } from '@mantine/core';

/**
 * A placeholder for a page that a later ticket builds, so each nav link opens a page
 * with its own title instead of another page's content.
 */
export default function ComingSoon({ title }: { title: string }) {
  return (
    <Container size="lg" py="md">
      <Paper withBorder p="lg" radius="md">
        <Title order={2} size="h3" mb="xs">
          {title}
        </Title>
        <Text c="dimmed">Coming soon.</Text>
      </Paper>
    </Container>
  );
}
