/**
 * Test data for the Results & History tests: the signed-in patient, their sessions and
 * results as the API returns them, and a fake API that answers by path. The ids are made
 * up.
 */
import { act } from '@testing-library/react';
import { vi } from 'vitest';

import type {
  AnalysisResult,
  ExerciseProgress,
  MeResponse,
  PlanExerciseResponse,
  ProgressPoint,
  SessionResponse,
  SessionResultResponse,
  SessionSummary,
} from '@/api/model';
import { PLANK, SQUAT } from './testPlan';

/** The signed-in patient (GET /me). Their id is the patient id in the results routes. */
export const ME: MeResponse = {
  id: '3f6c1a52-8e0b-4d4e-9a77-2c1d5b9e0f41',
  email: 'pat@example.com',
  role: 'patient',
};

export const SESSIONS_PATH = `/patients/${ME.id}/sessions`;
export const PROGRESS_PATH = `/patients/${ME.id}/progress`;

/** GET /sessions/{id}/result, for a session of this list. */
export const resultApiPath = (session: { id: string }) => `/sessions/${session.id}/result`;
/** GET /sessions/{id}, the status that useSessionStatus polls. */
export const statusApiPath = (session: { id: string }) => `/sessions/${session.id}`;

/**
 * What the AI service answers for every exercise done in reps until that exercise has an
 * analyzer: stub_rep_result in ai/app/main.py, with its "-stub" version.
 */
export const STUB_REPS_RESULT: AnalysisResult = {
  status: 'complete',
  rep_count: 3,
  hold_seconds: null,
  form_score: 97,
  reps: [
    {
      index: 1,
      start_seconds: 1.2,
      end_seconds: 3.9,
      side: null,
      score: 100,
      issues: [],
      metrics: {},
    },
    {
      index: 2,
      start_seconds: 4.4,
      end_seconds: 6.1,
      side: null,
      score: 90,
      issues: [{ code: 'too_fast', message: 'This rep took less than 2 seconds.' }],
      metrics: {},
    },
    {
      index: 3,
      start_seconds: 6.8,
      end_seconds: 9.6,
      side: null,
      score: 100,
      issues: [],
      metrics: {},
    },
  ],
  feedback: ['Slow down: take at least 2 seconds for each rep.'],
  error_code: null,
  error_message: null,
  analyzer_version: '0.4.0-stub',
};

/** The AI service's made-up plank result (stub_hold_result in ai/app/main.py). */
export const STUB_HOLD_RESULT: AnalysisResult = {
  status: 'complete',
  rep_count: null,
  hold_seconds: 22.0,
  form_score: 77,
  reps: [
    {
      index: 1,
      start_seconds: 2.0,
      end_seconds: 24.0,
      side: null,
      score: 77,
      issues: [{ code: 'hips_sagging', message: 'Your hips dropped below your shoulders.' }],
      metrics: { good_form_seconds: 17.0 },
    },
  ],
  feedback: ['Squeeze your glutes to keep your hips level with your shoulders.'],
  error_code: null,
  error_message: null,
  analyzer_version: '0.4.0-stub',
};

/** A zero-reps squat: complete, with no rep counted and no score. */
export const ZERO_REPS_RESULT: AnalysisResult = {
  ...STUB_REPS_RESULT,
  rep_count: 0,
  form_score: null,
  reps: [],
  feedback: [
    "We didn't see a full rep or hold. Keep your whole body in the frame and finish each one.",
  ],
};

/** A failure the AI service reports (docs/analysis-result-examples/failed-no-person.json). */
export const NO_PERSON_RESULT: AnalysisResult = {
  status: 'failed',
  rep_count: null,
  hold_seconds: null,
  form_score: null,
  reps: [],
  feedback: [],
  error_code: 'no_person',
  error_message:
    "We couldn't find a person in your video. Make sure your whole body is in the frame.",
  analyzer_version: '0.4.0',
};

/** A session in the list (GET /patients/{id}/sessions) of an exercise of the test plan. */
function summary(
  id: string,
  planExercise: PlanExerciseResponse,
  status: SessionSummary['status'],
  createdAt: string,
): SessionSummary {
  return {
    id,
    plan_exercise_id: planExercise.id,
    exercise_name: planExercise.exercise.name,
    exercise_display_name: planExercise.exercise.display_name,
    status,
    created_at: createdAt,
  };
}

// Newest first, as the API lists them.
export const PROCESSING_SQUAT = summary(
  'a1b2c3d4-0005-4e5f-8a9b-0c1d2e3f4a5b',
  SQUAT,
  'processing',
  '2026-11-14T16:20:00Z',
);
export const FAILED_SQUAT = summary(
  'a1b2c3d4-0004-4e5f-8a9b-0c1d2e3f4a5b',
  SQUAT,
  'failed',
  '2026-11-13T15:10:00Z',
);
export const COMPLETE_PLANK = summary(
  'a1b2c3d4-0003-4e5f-8a9b-0c1d2e3f4a5b',
  PLANK,
  'complete',
  '2026-11-12T14:00:00Z',
);
export const ZERO_REPS_SQUAT = summary(
  'a1b2c3d4-0002-4e5f-8a9b-0c1d2e3f4a5b',
  SQUAT,
  'complete',
  '2026-11-11T13:00:00Z',
);
export const COMPLETE_SQUAT = summary(
  'a1b2c3d4-0001-4e5f-8a9b-0c1d2e3f4a5b',
  SQUAT,
  'complete',
  '2026-11-10T12:00:00Z',
);

/** The session's result (GET /sessions/{id}/result): null while it is processing. */
export function withResult(
  session: SessionSummary,
  result: AnalysisResult | null,
): SessionResultResponse {
  return { ...session, status: result ? result.status : 'processing', result };
}

/** The session's status (GET /sessions/{id}), as useSessionStatus polls it. */
export function statusOf(
  session: SessionSummary,
  status: SessionResponse['status'],
): SessionResponse {
  return {
    id: session.id,
    plan_exercise_id: session.plan_exercise_id,
    status,
    created_at: session.created_at,
  };
}

/** A point of GET /patients/{id}/progress: the numbers of one complete session. */
export function pointOf(session: SessionSummary, result: AnalysisResult): ProgressPoint {
  return {
    session_id: session.id,
    created_at: session.created_at,
    form_score: result.form_score,
    rep_count: result.rep_count,
    hold_seconds: result.hold_seconds,
    analyzer_version: result.analyzer_version ?? '',
  };
}

/** GET /patients/{id}/progress: one entry per exercise, with its sessions oldest first. */
export function progressOf(
  ...entries: [planExercise: PlanExerciseResponse, points: ProgressPoint[]][]
): ExerciseProgress[] {
  return entries.map(([planExercise, points]) => ({
    exercise_name: planExercise.exercise.name,
    exercise_display_name: planExercise.exercise.display_name,
    exercise_kind: planExercise.exercise.kind,
    sessions: points,
  }));
}

type Answer = [status: number, body: unknown];

/**
 * Replaces fetch with a fake API that answers by path, so the tests need no backend.
 * Each path gets its answers one per request, and the last one again after that. A
 * request for any other path fails, like an API that can't be reached.
 */
export function fakeResultsApi(answers: Record<string, Answer[]>) {
  const counts = new Map<string, number>();
  const api = vi.fn<typeof fetch>(async (input) => {
    const path = new URL(String(input)).pathname;
    const list = answers[path];
    if (!list) {
      throw new Error(`The fake API has no answer for ${path}`);
    }
    const count = counts.get(path) ?? 0;
    counts.set(path, count + 1);
    const [status, body] = list[Math.min(count, list.length - 1)];
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', api);
  return api;
}

/** How many requests the fake API got for this path. */
export function requestsTo(api: ReturnType<typeof fakeResultsApi>, path: string): number {
  return api.mock.calls.filter(([input]) => new URL(String(input)).pathname === path).length;
}

/**
 * With fake timers (vi.useFakeTimers), lets them run for ms, then a little longer, so
 * React Query delivers what they started. A request that waits on the one before (GET
 * /me, then the list, then a poll) starts only once the page has rendered the answer
 * before it, so this takes a few rounds of act(). Each round moves the clock on a
 * little: React Query delivers an answer with a zero-delay timer, which fake timers run
 * only once the clock moves.
 */
export const advance = async (ms: number) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
  for (let round = 0; round < 5; round++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
  }
};
