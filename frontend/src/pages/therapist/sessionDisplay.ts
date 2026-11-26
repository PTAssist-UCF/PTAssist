/**
 * Helpers for the therapist pages that show a patient's sessions: the patient list, the
 * patient detail page, and a session's result page. Their addresses, how dates show, and
 * what the API's answers mean.
 */
import type { AnalysisResult } from '@/api/model';
import { ApiError } from '@/apiClient';

/** A linked patient's detail page, with their sessions. */
export function patientPath(patientId: string): string {
  return `/therapist/patients/${patientId}`;
}

/** One session's result, under its patient's detail page. */
export function sessionPath(patientId: string, sessionId: string): string {
  return `${patientPath(patientId)}/sessions/${sessionId}`;
}

/** A date and time in the browser's language, for example "Nov 10, 2026, 3:00 PM". */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

/** A date in the browser's language, for example "Nov 10, 2026". */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' });
}

/**
 * Whether the API refused to show a patient's sessions or a session's result. It answers
 * 404 for a patient who isn't linked to the therapist or is no longer a patient, and for a
 * session it won't show, the same as for an id that doesn't exist (backend/README.md,
 * Sessions, results, and progress). A 403 means the same to these pages.
 */
export function isAccessDenied(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 403 || error.status === 404);
}

/**
 * Whether a result is made up. Until the AI service can analyze an exercise, it answers
 * with a made-up result whose analyzer version ends in "-stub" (STUB_VERSION in
 * ai/app/main.py; docs/analysis-result.md, Versions), so it is never taken for a real one.
 */
export function isStubResult(result: AnalysisResult): boolean {
  return result.analyzer_version?.endsWith('-stub') ?? false;
}
