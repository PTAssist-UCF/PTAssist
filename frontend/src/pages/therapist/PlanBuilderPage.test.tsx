import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { focusManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';

import PlanBuilderPage from './PlanBuilderPage';
import { getGetPatientPlanQueryKey } from '@/api/plans';
import type { ExerciseResponse, PlanResponse } from '@/api/model';

const PATIENT = {
  id: '0b6f3c2e-5d1a-4c8e-9f7b-2a4d6e8c0f13',
  email: 'pat@example.com',
  linked_at: '2026-11-10T12:00:00Z',
};
const PLAN_PATH = `/therapist/patients/${PATIENT.id}/plan`;
// A second linked patient, with a plan of their own.
const OTHER_PATIENT = {
  id: '7c2e9a41-3b5d-4f60-8e1a-9d3c5b7f2e04',
  email: 'sam@example.com',
  linked_at: '2026-11-11T08:30:00Z',
};
const OTHER_PLAN_PATH = `/therapist/patients/${OTHER_PATIENT.id}/plan`;

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

/**
 * A plan for this patient. Each item is an exercise with its target (reps, or seconds for
 * one held for time), sets, and times per week, in the library's order.
 */
function planOf(patientId: string, items: [ExerciseResponse, number, number, number][]) {
  const plan: PlanResponse = {
    id: `plan-${patientId}`,
    patient_id: patientId,
    created_at: '2026-11-11T09:00:00Z',
    exercises: items.map(([exercise, target, sets, timesPerWeek]) => ({
      id: `${patientId}-${exercise.name}`,
      exercise,
      reps: exercise.kind === 'reps' ? target : null,
      hold_seconds: exercise.kind === 'hold' ? target : null,
      sets,
      times_per_week: timesPerWeek,
    })),
  };
  return plan;
}

/** The patient's saved plan: the plank and the squat. */
const PLAN = planOf(PATIENT.id, [
  [PLANK, 30, 3, 5],
  [SQUAT, 10, 2, 3],
]);
/** The same plan after another therapist added the cat-cow and changed the squat's reps. */
const NEWER_PLAN = planOf(PATIENT.id, [
  [CAT_COW, 8, 1, 2],
  [PLANK, 30, 3, 5],
  [SQUAT, 12, 2, 3],
]);
/** The other patient's plan: the cat-cow only. */
const OTHER_PLAN = planOf(OTHER_PATIENT.id, [[CAT_COW, 6, 1, 4]]);

// The API's two 404 answers for a plan (backend/app/routes/plans.py).
const NO_PLAN = { status: 404, body: { detail: 'This patient has no plan yet' } };
const NOT_FOUND = { status: 404, body: { detail: 'Patient not found' } };

type Answer = { status: number; body?: unknown };

/** The fake API's answers, by method and path. A test can change them as it goes. */
let answers: Record<string, Answer | Promise<Answer>>;

/**
 * A fake API, so the tests need no backend. Each request gets the answer for its method
 * and path; one with no answer fails like an unreachable API.
 */
function fakeApi(overrides: Record<string, Answer> = {}) {
  answers = {
    'GET /therapist/patients': { status: 200, body: [PATIENT, OTHER_PATIENT] },
    'GET /exercises': { status: 200, body: EXERCISES },
    [`GET ${PLAN_PATH}`]: { status: 200, body: PLAN },
    [`GET ${OTHER_PLAN_PATH}`]: { status: 200, body: OTHER_PLAN },
    ...overrides,
  };
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

/** From now on, the fake API gives this answer, for example after someone else saved. */
function setAnswer(request: string, answer: Answer | Promise<Answer>) {
  answers[request] = answer;
}

/** How many times the page asked for this patient's plan. */
function planRequests(api: ReturnType<typeof fakeApi>) {
  return api.mock.calls.filter(
    ([url, init]) => init?.method === 'GET' && new URL(String(url)).pathname === PLAN_PATH,
  ).length;
}

/** The therapist goes to another tab and comes back, so the page refetches its data. */
function switchTabsAndBack() {
  act(() => {
    focusManager.setFocused(false);
    focusManager.setFocused(true);
  });
}

/** The body of the PUT that saved the plan, or undefined if nothing was saved. */
function savedBody(api: ReturnType<typeof fakeApi>) {
  const call = api.mock.calls.find(([, init]) => init?.method === 'PUT');
  return call && { url: String(call[0]), body: JSON.parse(String(call[1]?.body)) };
}

/**
 * Opens the page at this address. `cached` plans are already in the cache, as when the
 * therapist opened those patients before.
 */
function renderPage(path = PLAN_PATH, { cached = [] }: { cached?: PlanResponse[] } = {}) {
  // retry: false, so a failed request fails at once instead of being retried.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  for (const plan of cached) {
    queryClient.setQueryData(getGetPatientPlanQueryKey(plan.patient_id), plan);
  }
  render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter initialEntries={[path]}>
          {/* Opens another patient's plan builder straight from this one, as the address
              bar or a link elsewhere in the app can. */}
          <Link to={OTHER_PLAN_PATH}>Open the other patient&apos;s plan</Link>
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
  focusManager.setFocused(undefined); // back to following the page's visibility
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
    const saved = planOf(PATIENT.id, [
      [PLANK, 45, 2, 5],
      [SQUAT, 12, 3, 4],
    ]);
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
    // The page's own save is not taken for someone else's.
    expect(screen.queryByText('This plan changed while you were editing it')).toBeNull();
    expect(field('Squat', 'Reps per set').value).toBe('12');
  });

  it('saves the changes to an existing plan, leaving out an exercise taken out', async () => {
    const saved = planOf(PATIENT.id, [[SQUAT, 15, 2, 3]]);
    const api = fakeApi({ [`PUT ${PLAN_PATH}`]: { status: 200, body: saved } });
    renderPage();
    await screen.findByRole('heading', { name: 'Plan for pat@example.com' });

    fireEvent.click(checkbox('Plank'));
    type('Squat', 'Reps per set', '15');
    fireEvent.click(saveButton());

    expect(await screen.findByText('Plan saved')).toBeDefined();
    expect(savedBody(api)?.body).toEqual({
      exercises: [{ exercise_id: SQUAT.id, reps: 15, sets: 2, times_per_week: 3 }],
    });
    expect(screen.queryByText('This plan changed while you were editing it')).toBeNull();
    expect(field('Squat', 'Reps per set').value).toBe('15');
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

describe('PlanBuilderPage, when the patient or their plan changes', () => {
  it("opens another patient's plan with their own exercises, even when both are cached", async () => {
    const api = fakeApi({ [`PUT ${OTHER_PLAN_PATH}`]: { status: 200, body: OTHER_PLAN } });
    renderPage(PLAN_PATH, { cached: [PLAN, OTHER_PLAN] });
    await screen.findByRole('heading', { name: 'Plan for pat@example.com' });
    type('Squat', 'Reps per set', '15'); // a change for the first patient, not saved

    // Straight to the other patient's plan builder: the page itself stays open.
    fireEvent.click(screen.getByRole('link', { name: "Open the other patient's plan" }));

    expect(await screen.findByRole('heading', { name: 'Plan for sam@example.com' })).toBeDefined();
    expect(checkbox('Cat-cow').checked).toBe(true);
    expect(field('Cat-cow', 'Reps per set').value).toBe('6');
    expect(checkbox('Squat').checked).toBe(false);
    fireEvent.click(saveButton());
    expect(await screen.findByText('Plan saved')).toBeDefined();
    expect(savedBody(api)).toEqual({
      url: `http://api.test${OTHER_PLAN_PATH}`,
      body: { exercises: [{ exercise_id: CAT_COW.id, reps: 6, sets: 1, times_per_week: 4 }] },
    });
  });

  it('shows a newer plan from a refetch when the form has no changes', async () => {
    // The cache still holds the plan from an earlier visit; the API has a newer one.
    const api = fakeApi({
      [`GET ${PLAN_PATH}`]: { status: 200, body: NEWER_PLAN },
      [`PUT ${PLAN_PATH}`]: { status: 200, body: NEWER_PLAN },
    });
    renderPage(PLAN_PATH, { cached: [PLAN] });

    await waitFor(() => expect(checkbox('Cat-cow').checked).toBe(true));
    expect(field('Squat', 'Reps per set').value).toBe('12');

    // A change now starts from the newer plan, so the save keeps the other changes.
    type('Plank', 'Hold time (seconds)', '40');
    fireEvent.click(saveButton());
    expect(await screen.findByText('Plan saved')).toBeDefined();
    expect(savedBody(api)?.body).toEqual({
      exercises: [
        { exercise_id: CAT_COW.id, reps: 8, sets: 1, times_per_week: 2 },
        { exercise_id: PLANK.id, hold_seconds: 40, sets: 3, times_per_week: 5 },
        { exercise_id: SQUAT.id, reps: 12, sets: 2, times_per_week: 3 },
      ],
    });
  });

  it('asks what to keep when a newer plan arrives while the form has changes', async () => {
    const saved = planOf(PATIENT.id, [
      [PLANK, 30, 3, 5],
      [SQUAT, 15, 2, 3],
    ]);
    const api = fakeApi({ [`PUT ${PLAN_PATH}`]: { status: 200, body: saved } });
    renderPage();
    await screen.findByRole('heading', { name: 'Plan for pat@example.com' });
    type('Squat', 'Reps per set', '15');

    // Meanwhile another therapist saves a newer plan, and the page refetches.
    setAnswer(`GET ${PLAN_PATH}`, { status: 200, body: NEWER_PLAN });
    switchTabsAndBack();

    expect(await screen.findByText('This plan changed while you were editing it')).toBeDefined();
    expect(field('Squat', 'Reps per set').value).toBe('15'); // the change is still there
    expect(saveButton().hasAttribute('disabled')).toBe(true);
    fireEvent.click(saveButton());
    expect(savedBody(api)).toBeUndefined();

    // Keeping the changes lets the therapist save them, in place of the newer plan.
    fireEvent.click(screen.getByRole('button', { name: 'Keep my changes' }));
    fireEvent.click(saveButton());
    expect(await screen.findByText('Plan saved')).toBeDefined();
    expect(savedBody(api)?.body).toEqual({
      exercises: [
        { exercise_id: PLANK.id, hold_seconds: 30, sets: 3, times_per_week: 5 },
        { exercise_id: SQUAT.id, reps: 15, sets: 2, times_per_week: 3 },
      ],
    });
  });

  it('loads the newer plan instead, when the therapist chooses it', async () => {
    fakeApi();
    renderPage();
    await screen.findByRole('heading', { name: 'Plan for pat@example.com' });
    type('Squat', 'Reps per set', '15');
    setAnswer(`GET ${PLAN_PATH}`, { status: 200, body: NEWER_PLAN });
    switchTabsAndBack();

    fireEvent.click(await screen.findByRole('button', { name: 'Load the newer version' }));

    expect(checkbox('Cat-cow').checked).toBe(true);
    expect(field('Squat', 'Reps per set').value).toBe('12');
    expect(screen.queryByText('This plan changed while you were editing it')).toBeNull();
    expect(saveButton().hasAttribute('disabled')).toBe(false);
  });

  it('keeps the saved plan when a refetch from before the save answers after it', async () => {
    const saved = planOf(PATIENT.id, [
      [PLANK, 30, 3, 5],
      [SQUAT, 15, 2, 3],
    ]);
    fakeApi({ [`PUT ${PLAN_PATH}`]: { status: 200, body: saved } });
    const { queryClient } = renderPage();
    await screen.findByRole('heading', { name: 'Plan for pat@example.com' });

    // A refetch starts, and its answer (the plan before the save) is slow to come.
    let answerLate: (answer: Answer) => void = () => {};
    setAnswer(`GET ${PLAN_PATH}`, new Promise<Answer>((resolve) => (answerLate = resolve)));
    switchTabsAndBack();
    await waitFor(() => expect(queryClient.isFetching()).toBeGreaterThan(0));

    type('Squat', 'Reps per set', '15');
    fireEvent.click(saveButton());
    expect(await screen.findByText('Plan saved')).toBeDefined();
    await act(async () => {
      answerLate({ status: 200, body: PLAN });
      await new Promise((resolve) => setTimeout(resolve, 20));
    });

    expect(field('Squat', 'Reps per set').value).toBe('15');
    expect(queryClient.getQueryData(getGetPatientPlanQueryKey(PATIENT.id))).toEqual(saved);
  });

  it('keeps the targets typed for a first plan while the page refetches', async () => {
    const api = fakeApi({ [`GET ${PLAN_PATH}`]: NO_PLAN });
    const { queryClient } = renderPage();
    await screen.findByText('No plan yet');
    fireEvent.click(checkbox('Squat'));
    type('Squat', 'Reps per set', '12');
    type('Squat', 'Sets', '3');

    // Switching tabs refetches the plan. Its answer takes a moment, as over a network,
    // and it is "no plan yet" again.
    let answerLate: (answer: Answer) => void = () => {};
    setAnswer(`GET ${PLAN_PATH}`, new Promise<Answer>((resolve) => (answerLate = resolve)));
    switchTabsAndBack();
    await waitFor(() => expect(planRequests(api)).toBe(2));
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));

    // The form stays while the request runs, and after its answer.
    expect(field('Squat', 'Reps per set').value).toBe('12');
    await act(async () => answerLate(NO_PLAN));
    await waitFor(() => expect(queryClient.isFetching()).toBe(0));
    expect(checkbox('Squat').checked).toBe(true);
    expect(field('Squat', 'Reps per set').value).toBe('12');
    expect(field('Squat', 'Sets').value).toBe('3');
  });

  it('says "Patient not found", not "no plan yet", when the API refuses the plan', async () => {
    // For example a linked user who is a therapist now: still in the list, but no plan.
    fakeApi({ [`GET ${PLAN_PATH}`]: NOT_FOUND });
    renderPage();

    expect(await screen.findByText('Patient not found')).toBeDefined();
    expect(screen.queryByText('No plan yet')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Save plan' })).toBeNull();
  });

  it('stops showing a cached plan once the API refuses it', async () => {
    fakeApi();
    renderPage();
    await screen.findByRole('heading', { name: 'Plan for pat@example.com' });

    setAnswer(`GET ${PLAN_PATH}`, NOT_FOUND);
    switchTabsAndBack();

    expect(await screen.findByText('Patient not found')).toBeDefined();
    expect(screen.queryByRole('checkbox', { name: 'Squat' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Save plan' })).toBeNull();
  });

  it('shows any other 404 as an error, not as an empty plan', async () => {
    fakeApi({ [`GET ${PLAN_PATH}`]: { status: 404, body: { detail: 'Not Found' } } });
    renderPage();

    expect(await screen.findByText("Couldn't load the plan")).toBeDefined();
    expect(screen.getByText('The API answered 404: Not Found')).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Save plan' })).toBeNull();
  });
});
