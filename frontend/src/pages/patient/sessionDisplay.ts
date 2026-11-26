/**
 * How the patient's Results & History pages describe a session (one uploaded video, one
 * set), and the addresses of those pages.
 */
import type { ProgressPoint, SessionStatus } from '@/api/model';

/** Results & History in the navigation: the patient's sessions, newest first. */
export const HISTORY_PATH = '/patient/history';

/**
 * The result page of one session. The upload page opens it after an upload, and each
 * session in Results & History links to it.
 */
export function resultPath(sessionId: string): string {
  return `${HISTORY_PATH}/${encodeURIComponent(sessionId)}`;
}

/** How each session status shows: a badge with this label and color. */
export const STATUS_BADGE: Record<SessionStatus, { label: string; color: string }> = {
  complete: { label: 'Complete', color: 'teal' },
  processing: { label: 'Processing', color: 'yellow' },
  failed: { label: 'Failed', color: 'red' },
};

/** When the video was uploaded, in the browser's language: "Nov 10, 2026, 3:00 PM". */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

/**
 * The headline number of a complete session: "3 reps", or "22.0 seconds held" for an
 * exercise held for time (the plank). Like ResultView, it shows the hold time whenever
 * hold_seconds is not null, because 0 is a real hold time.
 */
export function describeCount(point: Pick<ProgressPoint, 'rep_count' | 'hold_seconds'>): string {
  if (point.hold_seconds !== null) {
    return `${point.hold_seconds.toFixed(1)} seconds held`;
  }
  const reps = point.rep_count ?? 0;
  return `${reps} ${reps === 1 ? 'rep' : 'reps'}`;
}
