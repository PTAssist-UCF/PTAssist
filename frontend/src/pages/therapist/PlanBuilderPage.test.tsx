import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import PlanBuilderPage from './PlanBuilderPage';
import { getGetPatientPlanQueryKey } from '@/api/plans';
import type { ExerciseResponse, PlanResponse } from '@/api/model';

const PATIENT = {
  id: '0b6f3c2e-5d1a-4c8e-9f7b-2a4d6e8c0f13',
  email: 'pat@example.com',
  linked_at: '2026-11-10T12:00:00Z',
};
const PLAN_PATH = `/therapist/patients/${PATIENT.id}/plan`;

// The library, in its order (by display name): three done in reps, and one held for time.
const CAT_COW: ExerciseResponse = {
  id: 'e1c2a3b4-0000-4000-8000-000000000001',
  name: 'cat_cow',
  display_name: 'Cat-cow',
  kind: 'reps',
};
const PLANK: ExerciseResponse = {
  id: 'e1c2a3b4-0000-4000-8000-000000000002',
  name: 'plank',
  display_name: 'Plank',
  kind: 'hold',
};
const SIDE_LEG_RAISE: ExerciseResponse = {
  id: 'e1c2a3b4-0000-4000-8000-000000000004',
  name: 'side_leg_raise',
  display_name: 'Side-lying leg raise',
  kind: 'reps',
};
const SQUAT: ExerciseResponse = {
  id: 'e1c2a3b4-0000-4000-8000-000000000003',
  name: 'squat',
  display_name: 'Squat',
  kind: 'reps',
};
const EXERCISES = [CAT_COW, PLANK, SIDE_LEG_RAISE, SQUAT];

/** The patient's saved plan: the plank and the squat. */
const PLAN: PlanResponse = {
  id: 'a7d9c1e3-0000-4000-8000-0000000000aa',
  patient_id: PATIENT.id,
  created_at: '2026-11-11T09:00:00Z',
  exercises: [
    {
      id: 'pe-plank',
      exercise: PLANK,
      reps: null,
      hold_seconds: 30,
      sets: 3,
      times_per_week: 5,
    },
    { id: 'pe-squat', exercise: SQUAT, reps: 10, hold_seconds: null, sets: 2, times_per_week: 3 },
  ],
};

const NO_PLAN = { status: 404, body: { detail: 'This patient has no plan yet' } };

type Answer = { status: number; body?: unknown };

/**
 * A fake API, so the tests need no backend. Each request gets the answer for its method
 * and path; one with no answer fails like an unreachable API.
 */
function fakeApi(overrides: Record<string, Answer> = {}) {
  const answers: Record<string, Answer> = {
    'GET /therapist/patients': { status: 200, body: [PATIENT] },
    'GET /exercises': { status: 200, body: EXERCISES },
    [`GET ${PLAN_PATH}`]: { status: 200, body: PLAN },
    ...overrides,
  };
  const api = vi.fn<typeof fetch>(async (input, init) => {
    const request = `${init?.method ?? 'GET'} ${new URL(String(input)).pathname}`;
    const answer = answers[request];
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

/** The body of the PUT that saved the plan, or undefined if nothing was saved. */
function savedBody(api: ReturnType<typeof fakeApi>) {
  const call = api.mock.calls.find(([, init]) => init?.method === 'PUT');
  return call && { url: String(call[0]), body: JSON.parse(String(call[1]?.body)) };
}

function renderPage(path = PLAN_PATH) {
  // retry: false, so a failed request fails at once instead of being retried.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/therapist/patients/:patientId/plan" element={<PlanBuilderPage />} />
            <Route path="/therapist/plans" element={<div>Choose a patient</div>} />
          </Routes>
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
  return { queryClient };
}

/** The card of one exercise of the library. */
const card = (exercise: string) => within(screen.getByRole('group', { name: exercise }));
const checkbox = (exercise: string) =>
  card(exercise).getByRole('checkbox', { name: exercise }) as HTMLInputElement;
const field = (exercise: string, label: string) =>
  card(exercise).getByLabelText(label) as HTMLInputElement;
const type = (exercise: string, label: string, value: string) =>
  fireEvent.change(field(exercise, label), { target: { value } });
const saveButton = () => screen.getByRole('button', { name: 'Save plan' });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('PlanBuilderPage', () => {
  it("loads the patient's plan: its exercises are picked, with their targets", async () => {
    fakeApi();
    renderPage();

    // Who the plan is for.
    expect(await screen.findByRole('heading', { name: 'Plan for pat@example.com' })).toBeDefined();

    expect(checkbox('Squat').checked).toBe(true);
    expect(field('Squat', 'Reps per set').value).toBe('10');
    expect(field('Squat', 'Sets').value).toBe('2');
    expect(field('Squat', 'Times per week').value).toBe('3');

    expect(checkbox('Plank').checked).toBe(true);
    expect(field('Plank', 'Hold time (seconds)').value).toBe('30');
    expect(field('Plank', 'Sets').value).toBe('3');
    expect(field('Plank', 'Times per week').value).toBe('5');

    // Not in the plan: no targets to fill in.
    expect(checkbox('Cat-cow').checked).toBe(false);
    expect(card('Cat-cow').queryByLabelText('Reps per set')).toBeNull();
    expect(screen.queryByText('No plan yet')).toBeNull();
  });

  it('starts empty when the patient has no plan yet (404)', async () => {
    fakeApi({ [`GET ${PLAN_PATH}`]: NO_PLAN });
    renderPage();

    expect(await screen.findByText('No plan yet')).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Plan for pat@example.com' })).toBeDefined();
    for (const exercise of EXERCISES) {
      expect(checkbox(exercise.display_name).checked).toBe(false);
    }
    expect(saveButton()).toBeDefined();
  });

  it('asks for reps for an exercise done in reps, and a hold time for one held for time', async () => {
    fakeApi({ [`GET ${PLAN_PATH}`]: NO_PLAN });
    renderPage();
    await screen.findByText('No plan yet');

    fireEvent.click(checkbox('Squat'));
    fireEvent.click(checkbox('Plank'));

    expect(field('Squat', 'Reps per set')).toBeDefined();
    expect(card('Squat').queryByLabelText('Hold time (seconds)')).toBeNull();
    expect(card('Squat').getByText('Done in reps')).toBeDefined();

    expect(field('Plank', 'Hold time (seconds)')).toBeDefined();
    expect(card('Plank').queryByLabelText('Reps per set')).toBeNull();
    expect(card('Plank').getByText('Held for time')).toBeDefined();

    // Both kinds have sets and times per week.
    for (const exercise of ['Squat', 'Plank']) {
      expect(field(exercise, 'Sets')).toBeDefined();
      expect(field(exercise, 'Times per week')).toBeDefined();
    }
  });

  it('says that the reps of a side leg raise count both sides together', async () => {
    fakeApi({ [`GET ${PLAN_PATH}`]: NO_PLAN });
    renderPage();
    await screen.findByText('No plan yet');

    fireEvent.click(checkbox('Side-lying leg raise'));
    fireEvent.click(checkbox('Squat'));

    expect(card('Side-lying leg raise').getByText('Both sides together, 1 to 100')).toBeDefined();
    expect(card('Squat').getByText('1 to 100')).toBeDefined();
  });

  it('asks for at least one exercise before saving', async () => {
    const api = fakeApi({ [`GET ${PLAN_PATH}`]: NO_PLAN });
    renderPage();
    await screen.findByText('No plan yet');

    fireEvent.click(saveButton());

    expect(await screen.findByText('Pick at least one exercise for the plan.')).toBeDefined();
    expect(savedBody(api)).toBeUndefined();
  });

  it("checks every target against the backend's limits before saving", async () => {
    const api = fakeApi({ [`GET ${PLAN_PATH}`]: NO_PLAN });
    renderPage();
    await screen.findByText('No plan yet');

    fireEvent.click(checkbox('Squat'));
    type('Squat', 'Reps per set', '150'); // more than 100
    type('Squat', 'Sets', '0'); // less than 1
    // Times per week is left empty.
    fireEvent.click(checkbox('Plank'));
    type('Plank', 'Hold time (seconds)', '121'); // longer than one video (120 s)
    type('Plank', 'Sets', '11'); // more than 10
    type('Plank', 'Times per week', '8'); // more than 7
    fireEvent.click(saveButton());

    expect(
      await screen.findByText('Check the highlighted targets, then save again.'),
    ).toBeDefined();
    expect(card('Squat').getByText('Enter a whole number from 1 to 100.')).toBeDefined();
    expect(card('Squat').getByText('Enter a whole number from 1 to 10.')).toBeDefined();
    expect(card('Squat').getByText('Enter a whole number from 1 to 7.')).toBeDefined();
    expect(card('Plank').getByText('Enter a whole number from 1 to 120.')).toBeDefined();
    expect(card('Plank').getByText('Enter a whole number from 1 to 10.')).toBeDefined();
    expect(card('Plank').getByText('Enter a whole number from 1 to 7.')).toBeDefined();
    expect(savedBody(api)).toBeUndefined();

    // A fixed field loses its error at once.
    type('Squat', 'Reps per set', '12');
    expect(card('Squat').queryByText('Enter a whole number from 1 to 100.')).toBeNull();
  });

  it('saves the whole plan with one PUT, with reps or hold_seconds by kind', async () => {
    const saved: PlanResponse = { ...PLAN, exercises: [] };
    const api = fakeApi({
      [`GET ${PLAN_PATH}`]: NO_PLAN,
      [`PUT ${PLAN_PATH}`]: { status: 201, body: saved },
    });
    const { queryClient } = renderPage();
    await screen.findByText('No plan yet');

    fireEvent.click(checkbox('Squat'));
    type('Squat', 'Reps per set', '12');
    type('Squat', 'Sets', '3');
    type('Squat', 'Times per week', '4');
    fireEvent.click(checkbox('Plank'));
    type('Plank', 'Hold time (seconds)', '45');
    type('Plank', 'Sets', '2');
    type('Plank', 'Times per week', '5');
    fireEvent.click(saveButton());

    expect(await screen.findByText('Plan saved')).toBeDefined();
    expect(savedBody(api)).toEqual({
      url: `http://api.test${PLAN_PATH}`,
      body: {
        exercises: [
          { exercise_id: PLANK.id, hold_seconds: 45, sets: 2, times_per_week: 5 },
          { exercise_id: SQUAT.id, reps: 12, sets: 3, times_per_week: 4 },
        ],
      },
    });
    // The saved plan replaces the cached one, so the page now has a plan.
    expect(queryClient.getQueryData(getGetPatientPlanQueryKey(PATIENT.id))).toEqual(saved);
    expect(screen.queryByText('No plan yet')).toBeNull();
  });

  it('saves the changes to an existing plan, leaving out an exercise taken out', async () => {
    const api = fakeApi({ [`PUT ${PLAN_PATH}`]: { status: 200, body: PLAN } });
    renderPage();
    await screen.findByRole('heading', { name: 'Plan for pat@example.com' });

    fireEvent.click(checkbox('Plank'));
    type('Squat', 'Reps per set', '15');
    fireEvent.click(saveButton());

    expect(await screen.findByText('Plan saved')).toBeDefined();
    expect(savedBody(api)?.body).toEqual({
      exercises: [{ exercise_id: SQUAT.id, reps: 15, sets: 2, times_per_week: 3 }],
    });
  });

  it("explains a 409: an exercise with uploaded videos can't be taken out", async () => {
    const detail =
      "Nothing was saved. These exercises can't be removed from the plan, because the " +
      'patient has uploaded videos for them and their results are kept: Plank. You can ' +
      'change their targets instead.';
    fakeApi({ [`PUT ${PLAN_PATH}`]: { status: 409, body: { detail } } });
    renderPage();
    await screen.findByRole('heading', { name: 'Plan for pat@example.com' });

    fireEvent.click(checkbox('Plank'));
    fireEvent.click(saveButton());

    expect(await screen.findByText("Some exercises can't be removed from the plan")).toBeDefined();
    expect(screen.getByText(detail)).toBeDefined();
    expect(
      screen.getByText('Pick those exercises again to keep them in the plan, then save.'),
    ).toBeDefined();
    expect(screen.queryByText('Plan saved')).toBeNull();

    // A new change hides the message.
    fireEvent.click(checkbox('Plank'));
    expect(screen.queryByText(detail)).toBeNull();
  });

  it.each([
    [
      404,
      { detail: 'Patient not found' },
      'Patient not found',
      'Nothing was saved. This patient is no longer linked to you.',
    ],
    [
      422,
      { detail: 'Plank is held for time, so its target is hold_seconds, not reps' },
      'The plan was not saved',
      'Plank is held for time, so its target is hold_seconds, not reps',
    ],
    [
      422,
      { detail: [{ loc: ['body', 'exercises'], msg: 'Field required', type: 'missing' }] },
      'The plan was not saved',
      "The API didn't accept these targets. Check them and try again.",
    ],
    [
      500,
      { detail: 'Server error' },
      'The plan was not saved',
      'The API answered 500: Server error',
    ],
  ])('explains a %i answer to the save', async (status, body, title, message) => {
    fakeApi({ [`PUT ${PLAN_PATH}`]: { status, body } });
    renderPage();
    await screen.findByRole('heading', { name: 'Plan for pat@example.com' });

    fireEvent.click(saveButton());

    expect(await screen.findByText(title)).toBeDefined();
    expect(screen.getByText(message)).toBeDefined();
  });

  it('says so when the patient is not linked, without asking for a plan', async () => {
    const api = fakeApi({ 'GET /therapist/patients': { status: 200, body: [] } });
    renderPage();

    expect(await screen.findByText('Patient not found')).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Save plan' })).toBeNull();
    expect(api.mock.calls.some(([url]) => String(url).endsWith('/plan'))).toBe(false);

    fireEvent.click(screen.getByRole('link', { name: 'Choose one of your patients' }));
    expect(await screen.findByText('Choose a patient')).toBeDefined();
  });

  it.each([
    ['the exercise library', { 'GET /exercises': { status: 500, body: { detail: 'Boom' } } }],
    ['the patients', { 'GET /therapist/patients': { status: 500, body: { detail: 'Boom' } } }],
  ])("shows an error when %s can't load", async (_, overrides) => {
    fakeApi(overrides);
    renderPage();

    expect(await screen.findByText("Couldn't load the plan builder")).toBeDefined();
    expect(screen.getByText('The API answered 500: Boom')).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Save plan' })).toBeNull();
  });

  it("shows an error when the plan can't load, other than no plan yet", async () => {
    fakeApi({ [`GET ${PLAN_PATH}`]: { status: 500, body: { detail: 'Boom' } } });
    renderPage();

    expect(await screen.findByText("Couldn't load the plan")).toBeDefined();
    expect(screen.getByText('The API answered 500: Boom')).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Save plan' })).toBeNull();
  });

  it('shows a loading message until the plan has loaded', async () => {
    vi.stubGlobal('fetch', () => new Promise(() => {}));
    renderPage();

    expect(screen.getByText('Loading the plan…')).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Save plan' })).toBeNull();
  });

  it('links back to the list of patients', async () => {
    fakeApi();
    renderPage();

    fireEvent.click(await screen.findByRole('link', { name: 'Choose another patient' }));

    expect(await screen.findByText('Choose a patient')).toBeDefined();
  });
});
