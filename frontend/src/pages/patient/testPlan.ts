/**
 * Test data for the patient page tests: plans as GET /plans/me returns them, and a fake
 * API that answers with them. The ids and targets are made up.
 */
import { vi } from 'vitest';

import type { PlanExerciseResponse, PlanResponse } from '@/api/model';

export const SQUAT: PlanExerciseResponse = {
  id: '4e8bbd2a-8141-4176-b3aa-5a896d8e27aa',
  exercise: {
    id: '0b6f8e1c-2d3a-4f5b-8c7d-9e0f1a2b3c4d',
    name: 'squat',
    display_name: 'Squat',
    kind: 'reps',
  },
  reps: 10,
  hold_seconds: null,
  sets: 3,
  times_per_week: 3,
};

export const PLANK: PlanExerciseResponse = {
  id: '9a1c2b3d-4e5f-4a6b-8c7d-0e1f2a3b4c5d',
  exercise: {
    id: '7d6c5b4a-3f2e-4d1c-9b0a-8f7e6d5c4b3a',
    name: 'plank',
    display_name: 'Plank',
    kind: 'hold',
  },
  reps: null,
  hold_seconds: 30,
  sets: 3,
  times_per_week: 5,
};

/** A plan with these exercises. */
export function planWith(...exercises: PlanExerciseResponse[]): PlanResponse {
  return {
    id: '2c4e6a8b-1d3f-4b5a-9c7e-0f2a4c6e8b1d',
    patient_id: '3f6c1a52-8e0b-4d4e-9a77-2c1d5b9e0f41',
    created_at: '2026-11-10T12:00:00Z',
    exercises,
  };
}

/** What GET /plans/me answers (with a 404) when the patient has no plan yet. */
export const NO_PLAN = {
  detail: "You don't have a plan yet. Your therapist will make one for you.",
};

/**
 * Replaces fetch with a fake API, so the tests need no backend. GET /plans/me gets these
 * answers, one per request, and the last one again after that. Any other request fails.
 */
export function fakePlanApi(...answers: [status: number, body: unknown][]) {
  let requests = 0;
  const api = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (!url.endsWith('/plans/me')) {
      throw new Error(`The fake API has no answer for ${url}`);
    }
    const [status, body] = answers[Math.min(requests, answers.length - 1)];
    requests += 1;
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', api);
  return api;
}
