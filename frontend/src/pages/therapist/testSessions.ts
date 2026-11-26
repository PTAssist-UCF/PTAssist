/**
 * Test data for the patient detail and session result page tests: linked patients, their
 * sessions, and results as the API sends them, and a fake API that answers with them. The
 * patients and ids are made up; the results are the examples in
 * docs/analysis-result-examples/.
 */
import { vi } from 'vitest';

import type {
  AnalysisResult,
  LinkedPatientResponse,
  SessionResultResponse,
  SessionStatus,
  SessionSummary,
} from '@/api/model';
import squat from '../../../../docs/analysis-result-examples/squat.json';
import plank from '../../../../docs/analysis-result-examples/plank.json';
import sideLegRaise from '../../../../docs/analysis-result-examples/side-leg-raise.json';
import failedNoPerson from '../../../../docs/analysis-result-examples/failed-no-person.json';
import failedTimedOut from '../../../../docs/analysis-result-examples/failed-timed-out.json';

// Synthetic patients, in the order the API lists them (by email).
export const ANA: LinkedPatientResponse = {
  id: '0b6f3c2e-1a4d-4c8e-9f21-5d7a8b9c0e11',
  email: 'ana@example.com',
  linked_at: '2026-11-01T15:00:00Z',
};
export const BEN: LinkedPatientResponse = {
  id: '1c7a4d3f-2b5e-4d9f-8a32-6e8b9c0d1f22',
  email: 'ben@example.com',
  linked_at: '2026-11-02T15:00:00Z',
};
/** A patient the therapist isn't linked to. */
export const UNLINKED_PATIENT_ID = '5a1e8b7d-6f9c-4b3d-8e76-0c2f3a4b5d66';

// The example results, with the API's types. (A JSON import has plain strings where the
// API's type lists the values, such as "complete" or "failed".)
export const SQUAT_RESULT = squat as AnalysisResult;
export const PLANK_RESULT = plank as AnalysisResult;
export const SIDE_LEG_RAISE_RESULT = sideLegRaise as AnalysisResult;
export const FAILED_NO_PERSON = failedNoPerson as AnalysisResult;
export const FAILED_TIMED_OUT = failedTimedOut as AnalysisResult;
/**
 * A made-up result, as the AI service sends for an exercise it can't analyze yet: its
 * version ends in "-stub" (stub_rep_result in ai/app/main.py).
 */
export const STUB_RESULT: AnalysisResult = { ...SQUAT_RESULT, analyzer_version: '0.4.0-stub' };

/** The exercises the sessions are for: name in the API, and display name. */
const EXERCISES = {
  squat: 'Squat',
  plank: 'Plank',
  side_leg_raise: 'Side-lying leg raise',
} as const;

/** A session in a patient's list (GET /patients/{patient_id}/sessions). */
export function session(
  id: string,
  status: SessionStatus,
  createdAt: string,
  exercise: keyof typeof EXERCISES = 'squat',
): SessionSummary {
  return {
    id,
    plan_exercise_id: `plan-exercise-${exercise}`,
    exercise_name: exercise,
    exercise_display_name: EXERCISES[exercise],
    status,
    created_at: createdAt,
  };
}

/** The answer to GET /sessions/{session_id}/result: the session, with its result. */
export function withResult(
  summary: SessionSummary,
  result: AnalysisResult | null,
): SessionResultResponse {
  return { ...summary, result };
}

// Ana's sessions, newest first: a side-lying leg raise she just uploaded, still
// processing; a squat with its result; and a plank that failed.
export const ANA_LEG_RAISE = session(
  'a1b2c3d4-0000-4000-8000-000000000003',
  'processing',
  '2026-11-12T15:00:00Z',
  'side_leg_raise',
);
export const ANA_SQUAT = session(
  'a1b2c3d4-0000-4000-8000-000000000002',
  'complete',
  '2026-11-11T15:00:00Z',
  'squat',
);
export const ANA_PLANK = session(
  'a1b2c3d4-0000-4000-8000-000000000001',
  'failed',
  '2026-11-10T15:00:00Z',
  'plank',
);
export const ANA_SESSIONS = [ANA_LEG_RAISE, ANA_SQUAT, ANA_PLANK];
/** Ben's only session: a plank, with its result. */
export const BEN_PLANK = session(
  'b2c3d4e5-0000-4000-8000-000000000001',
  'complete',
  '2026-11-09T15:00:00Z',
  'plank',
);

/** The fake API's answer to one request: a status and a JSON body. */
export type Answer = { status: number; body?: unknown };

/** The fake API's answers, by method and path, for example "GET /therapist/patients". */
export type Answers = Record<string, Answer | Promise<Answer>>;

/**
 * The API as a therapist with Ana and Ben linked sees it: their lists, their sessions, and
 * each session's result. Like the real API, it shows Ben's session to this therapist,
 * who is linked to Ben too, so a page that asked for it at an address of Ana's would get
 * it. `overrides` replaces some of the answers.
 */
export function apiAnswers(overrides: Answers = {}): Answers {
  return {
    'GET /therapist/patients': { status: 200, body: [ANA, BEN] },
    [`GET /patients/${ANA.id}/sessions`]: { status: 200, body: ANA_SESSIONS },
    [`GET /patients/${BEN.id}/sessions`]: { status: 200, body: [BEN_PLANK] },
    [`GET /sessions/${ANA_LEG_RAISE.id}/result`]: {
      status: 200,
      body: withResult(ANA_LEG_RAISE, null),
    },
    [`GET /sessions/${ANA_SQUAT.id}/result`]: {
      status: 200,
      body: withResult(ANA_SQUAT, SQUAT_RESULT),
    },
    [`GET /sessions/${ANA_PLANK.id}/result`]: {
      status: 200,
      body: withResult(ANA_PLANK, FAILED_NO_PERSON),
    },
    [`GET /sessions/${BEN_PLANK.id}/result`]: {
      status: 200,
      body: withResult(BEN_PLANK, PLANK_RESULT),
    },
    ...overrides,
  };
}

/**
 * Replaces fetch with a fake API, so the tests need no backend. Each request gets the
 * answer for its method and path, looked up when the request arrives, so a test can change
 * the answers as it goes. A request with no answer fails like an unreachable API.
 */
export function fakeApi(answers: Answers) {
  const api = vi.fn<typeof fetch>(async (input, init) => {
    const request = `${init?.method ?? 'GET'} ${new URL(String(input)).pathname}`;
    const answer = await answers[request];
    if (!answer) {
      throw new TypeError(`No fake answer for ${request}`);
    }
    return new Response(answer.body === undefined ? null : JSON.stringify(answer.body), {
      status: answer.status,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', api);
  return api;
}

/** How many GET requests the page sent to this path. */
export function requestsTo(api: ReturnType<typeof fakeApi>, path: string): number {
  return api.mock.calls.filter(
    ([input, init]) =>
      (init?.method ?? 'GET') === 'GET' && new URL(String(input)).pathname === path,
  ).length;
}
