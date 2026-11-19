import { ApiError } from '@/apiClient';

/**
 * What to show when an API call fails: the API's own sentence when it sent one (FastAPI
 * puts it in `detail`), or a short general message.
 */
export function apiErrorText(error: unknown): string {
  // No status at all: the API is down, the browser is offline, or CORS hid the answer.
  if (!(error instanceof ApiError)) {
    return 'Could not reach the API. Check your connection and try again.';
  }
  const detail = (error.body as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' ? detail : `The API answered ${error.status}. Try again.`;
}
