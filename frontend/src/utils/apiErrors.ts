/**
 * Turns a failed API request into text a page can show.
 *
 * A generated hook's `error` is an ApiError when the API answered with an error, and a
 * plain Error when it could not be reached at all (see src/apiClient.ts).
 */
import { ApiError } from '@/apiClient';

/**
 * The API's own sentence about the error, if it gave one. FastAPI's HTTPException answers
 * with { "detail": "..." }. Its validation errors (422) have a list instead, so they
 * give undefined.
 */
export function apiErrorDetail(error: Error): string | undefined {
  if (!(error instanceof ApiError)) {
    return undefined;
  }
  const detail = (error.body as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' ? detail : undefined;
}

/** One sentence about a failed request: the API's answer, or that it didn't answer. */
export function describeApiError(error: Error): string {
  if (!(error instanceof ApiError)) {
    return 'No answer from the API. Check your connection and try again.';
  }
  const detail = apiErrorDetail(error);
  return detail
    ? `The API answered ${error.status}: ${detail}`
    : `The API answered ${error.status}.`;
}
