import { Badge } from '@mantine/core';

import type { SessionStatus } from '@/api/model';

/** The words and color of each session status, the same on every page that lists sessions. */
const STATUS_BADGE: Record<SessionStatus, { label: string; color: string }> = {
  complete: { label: 'Complete', color: 'teal' },
  processing: { label: 'Processing', color: 'yellow' },
  failed: { label: 'Failed', color: 'red' },
};

/** A session's status (processing, complete, or failed) as a small colored badge. */
export default function SessionStatusBadge({ status }: { status: SessionStatus }) {
  const { label, color } = STATUS_BADGE[status];
  return (
    <Badge color={color} variant="light">
      {label}
    </Badge>
  );
}
