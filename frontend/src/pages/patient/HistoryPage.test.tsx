import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

import { getGetMeQueryKey } from '@/api/me';
import { getGetPatientProgressQueryKey, getListPatientSessionsQueryKey } from '@/api/results';
import { POLL_INTERVAL_MS, POLL_TIMEOUT_MS } from '@/hooks/useSessionStatus';
import HistoryPage from './HistoryPage';
import { formatDateTime, resultPath } from './sessionDisplay';
import { PLANK, SQUAT } from './testPlan';
import {
  COMPLETE_PLANK,
  COMPLETE_SQUAT,
  FAILED_SQUAT,
  ME,
  PROCESSING_SQUAT,
  PROGRESS_PATH,
  SESSIONS_PATH,
  STUB_HOLD_RESULT,
  STUB_REPS_RESULT,
  ZERO_REPS_RESULT,
  ZERO_REPS_SQUAT,
  advance,
  fakeResultsApi,
  pointOf,
  progressOf,
  requestsTo,
  statusApiPath,
  statusOf,
} from './testSessions';

/** Every session of the test data, newest first, as GET /patients/{id}/sessions lists them. */
const ALL_SESSIONS = [
  PROCESSING_SQUAT,
  FAILED_SQUAT,
  COMPLETE_PLANK,
  ZERO_REPS_SQUAT,
  COMPLETE_SQUAT,
];

/** Their numbers (GET /patients/{id}/progress): only complete sessions, by exercise name. */
const ALL_PROGRESS = progressOf(
  [PLANK, [pointOf(COMPLETE_PLANK, STUB_HOLD_RESULT)]],
  [SQUAT, [pointOf(COMPLETE_SQUAT, STUB_REPS_RESULT), pointOf(ZERO_REPS_SQUAT, ZERO_REPS_RESULT)]],
);

/** The card of one session in the list. */
const card = (session: { id: string }) => screen.getByTestId(`session-${session.id}`);

describe('HistoryPage (Results & History)', () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  /** Opens Results & History, with stand-ins for the pages it links to. */
  function renderHistory(queryClient?: QueryClient) {
    // retry: false, so a failed request fails at once instead of being retried.
    const client =
      queryClient ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const router = createMemoryRouter(
      [
        { path: '/patient/history', element: <HistoryPage /> },
        { path: '/patient/history/:sessionId', element: <div>Session Result Page</div> },
        { path: '/patient', element: <div>My Plan Page</div> },
      ],
      { initialEntries: ['/patient/history'] },
    );
    render(
      <QueryClientProvider client={client}>
        <MantineProvider>
          <RouterProvider router={router} />
        </MantineProvider>
      </QueryClientProvider>,
    );
    return { router };
  }

  it("lists the patient's sessions newest first, each linking to its result page", async () => {
    const api = fakeResultsApi({
      '/me': [[200, ME]],
      [SESSIONS_PATH]: [[200, ALL_SESSIONS]],
      [PROGRESS_PATH]: [[200, ALL_PROGRESS]],
      [statusApiPath(PROCESSING_SQUAT)]: [[200, statusOf(PROCESSING_SQUAT, 'processing')]],
    });

    renderHistory();

    expect(screen.getByRole('heading', { name: 'Results & History' })).toBeDefined();
    await screen.findByTestId(`session-${COMPLETE_SQUAT.id}`);
    const links = screen
      .getAllByRole('link')
      .map((link) => link.getAttribute('href'))
      .filter((href) => href?.startsWith('/patient/history/'));
    expect(links).toEqual(ALL_SESSIONS.map((session) => resultPath(session.id)));
    // The patient's own id, from GET /me.
    expect(requestsTo(api, SESSIONS_PATH)).toBe(1);
    expect(requestsTo(api, PROGRESS_PATH)).toBe(1);

    fireEvent.click(card(COMPLETE_PLANK));

    expect(await screen.findByText('Session Result Page')).toBeDefined();
  });

  it('shows the exercise, date, status, and numbers of each session', async () => {
    fakeResultsApi({
      '/me': [[200, ME]],
      [SESSIONS_PATH]: [[200, ALL_SESSIONS]],
      [PROGRESS_PATH]: [[200, ALL_PROGRESS]],
      [statusApiPath(PROCESSING_SQUAT)]: [[200, statusOf(PROCESSING_SQUAT, 'processing')]],
    });

    renderHistory();

    // A squat with the AI service's made-up result: 3 reps, a good score.
    await waitFor(() => expect(within(card(COMPLETE_SQUAT)).getByText('3 reps')).toBeDefined());
    const squat = within(card(COMPLETE_SQUAT));
    expect(squat.getByText('Squat')).toBeDefined();
    expect(squat.getByText('Complete')).toBeDefined();
    expect(squat.getByTestId('session-score').textContent).toBe('97 · Good');
    expect(squat.getByTestId('session-score').getAttribute('data-band')).toBe('good');
    const date = card(COMPLETE_SQUAT).querySelector('time');
    expect(date?.getAttribute('dateTime')).toBe(COMPLETE_SQUAT.created_at);
    expect(date?.textContent).toBe(formatDateTime(COMPLETE_SQUAT.created_at));

    // A plank shows its hold time, not reps.
    const plank = within(card(COMPLETE_PLANK));
    expect(plank.getByText('Plank')).toBeDefined();
    expect(plank.getByText('22.0 seconds held')).toBeDefined();
    expect(plank.getByTestId('session-score').textContent).toBe('77 · Fair');

    // No rep seen: 0 reps, and no score (which is not a score of 0).
    const zeroReps = within(card(ZERO_REPS_SQUAT));
    expect(zeroReps.getByText('0 reps')).toBeDefined();
    expect(zeroReps.queryByTestId('session-score')).toBeNull();

    const failed = within(card(FAILED_SQUAT));
    expect(failed.getByText('Failed')).toBeDefined();
    expect(failed.getByText("We couldn't analyze this video. Open it to see why.")).toBeDefined();
    expect(failed.queryByTestId('session-score')).toBeNull();

    const processing = within(card(PROCESSING_SQUAT));
    expect(processing.getByText('Processing')).toBeDefined();
    expect(processing.getByText('Analyzing your video...')).toBeDefined();
  });

  it('polls a processing session, and shows its numbers once the analysis has finished', async () => {
    vi.useFakeTimers();
    const done = { ...PROCESSING_SQUAT, status: 'complete' as const };
    const api = fakeResultsApi({
      '/me': [[200, ME]],
      // Loaded again once the poll says the analysis has finished.
      [SESSIONS_PATH]: [
        [200, [PROCESSING_SQUAT, COMPLETE_SQUAT]],
        [200, [done, COMPLETE_SQUAT]],
      ],
      [PROGRESS_PATH]: [
        [200, progressOf([SQUAT, [pointOf(COMPLETE_SQUAT, STUB_REPS_RESULT)]])],
        [
          200,
          progressOf([
            SQUAT,
            [pointOf(COMPLETE_SQUAT, STUB_REPS_RESULT), pointOf(done, ZERO_REPS_RESULT)],
          ]),
        ],
      ],
      [statusApiPath(PROCESSING_SQUAT)]: [
        [200, statusOf(PROCESSING_SQUAT, 'processing')],
        [200, statusOf(PROCESSING_SQUAT, 'complete')],
      ],
    });

    renderHistory();
    await advance(0);

    expect(within(card(PROCESSING_SQUAT)).getByText('Processing')).toBeDefined();
    expect(within(card(PROCESSING_SQUAT)).getByText('Analyzing your video...')).toBeDefined();
    expect(requestsTo(api, statusApiPath(PROCESSING_SQUAT))).toBe(1);
    // Only the processing session is polled.
    expect(requestsTo(api, statusApiPath(COMPLETE_SQUAT))).toBe(0);

    await advance(POLL_INTERVAL_MS);

    const finished = within(card(PROCESSING_SQUAT));
    expect(finished.getByText('Complete')).toBeDefined();
    expect(finished.getByText('0 reps')).toBeDefined();
    expect(finished.queryByText('Analyzing your video...')).toBeNull();
    expect(requestsTo(api, SESSIONS_PATH)).toBe(2);
    expect(requestsTo(api, PROGRESS_PATH)).toBe(2);

    // Done: no more polling.
    await advance(POLL_INTERVAL_MS * 5);
    expect(requestsTo(api, statusApiPath(PROCESSING_SQUAT))).toBe(2);
  });

  it('says so when checking on a processing session fails, and points to its result page', async () => {
    vi.useFakeTimers();
    fakeResultsApi({
      '/me': [[200, ME]],
      [SESSIONS_PATH]: [[200, [PROCESSING_SQUAT]]],
      [PROGRESS_PATH]: [[200, []]],
      [statusApiPath(PROCESSING_SQUAT)]: [[503, { detail: 'Service unavailable' }]],
    });

    renderHistory();
    await advance(0);

    const stopped = within(card(PROCESSING_SQUAT));
    expect(
      stopped.getByText('We stopped checking on this video. Open it to check again.'),
    ).toBeDefined();
    expect(stopped.queryByText('Analyzing your video...')).toBeNull();
    expect(card(PROCESSING_SQUAT).getAttribute('href')).toBe(resultPath(PROCESSING_SQUAT.id));
  });

  it('says so when a processing session passes the polling timeout', async () => {
    vi.useFakeTimers();
    const api = fakeResultsApi({
      '/me': [[200, ME]],
      [SESSIONS_PATH]: [[200, [PROCESSING_SQUAT]]],
      [PROGRESS_PATH]: [[200, []]],
      [statusApiPath(PROCESSING_SQUAT)]: [[200, statusOf(PROCESSING_SQUAT, 'processing')]],
    });

    renderHistory();
    await advance(0);
    expect(within(card(PROCESSING_SQUAT)).getByText('Analyzing your video...')).toBeDefined();

    await advance(POLL_TIMEOUT_MS + POLL_INTERVAL_MS);

    expect(
      within(card(PROCESSING_SQUAT)).getByText(
        'We stopped checking on this video. Open it to check again.',
      ),
    ).toBeDefined();
    // Polling has stopped.
    const polls = requestsTo(api, statusApiPath(PROCESSING_SQUAT));
    await advance(POLL_INTERVAL_MS * 5);
    expect(requestsTo(api, statusApiPath(PROCESSING_SQUAT))).toBe(polls);
  });

  it('asks for the list again whenever the page opens, so a new upload shows up', async () => {
    // A cached list from an earlier visit, still fresh: without asking again, the page
    // would show it as it is. GET /me is cached too, as RoleRoute loads it first.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    queryClient.setQueryData(getGetMeQueryKey(), ME);
    queryClient.setQueryData(getListPatientSessionsQueryKey(ME.id), [COMPLETE_SQUAT]);
    queryClient.setQueryData(
      getGetPatientProgressQueryKey(ME.id),
      progressOf([SQUAT, [pointOf(COMPLETE_SQUAT, STUB_REPS_RESULT)]]),
    );
    // The video uploaded since then is processing.
    fakeResultsApi({
      '/me': [[200, ME]],
      [SESSIONS_PATH]: [[200, [PROCESSING_SQUAT, COMPLETE_SQUAT]]],
      [PROGRESS_PATH]: [[200, progressOf([SQUAT, [pointOf(COMPLETE_SQUAT, STUB_REPS_RESULT)]])]],
      [statusApiPath(PROCESSING_SQUAT)]: [[200, statusOf(PROCESSING_SQUAT, 'processing')]],
    });

    renderHistory(queryClient);

    expect(await screen.findByTestId(`session-${PROCESSING_SQUAT.id}`)).toBeDefined();
    expect(within(card(PROCESSING_SQUAT)).getByText('Processing')).toBeDefined();
    expect(within(card(COMPLETE_SQUAT)).getByText('3 reps')).toBeDefined();
  });

  it('says so when the patient has no sessions yet, and links to My Plan', async () => {
    fakeResultsApi({
      '/me': [[200, ME]],
      [SESSIONS_PATH]: [[200, []]],
      [PROGRESS_PATH]: [[200, []]],
    });

    renderHistory();

    expect(await screen.findByText('No sessions yet')).toBeDefined();
    const myPlan = screen.getByRole('link', { name: 'Go to My Plan' });
    expect(myPlan.getAttribute('href')).toBe('/patient');
    fireEvent.click(myPlan);
    expect(await screen.findByText('My Plan Page')).toBeDefined();
  });

  it('shows a spinner while the sessions load', () => {
    vi.stubGlobal('fetch', () => new Promise(() => {}));

    renderHistory();

    expect(screen.getByText('Loading your sessions...')).toBeDefined();
    expect(screen.queryByText('No sessions yet')).toBeNull();
  });

  it('shows why the sessions could not load, and loads them again on Try again', async () => {
    const api = fakeResultsApi({
      '/me': [[200, ME]],
      [SESSIONS_PATH]: [
        [500, { detail: 'Database unavailable' }],
        [200, [COMPLETE_SQUAT]],
      ],
      [PROGRESS_PATH]: [[200, progressOf([SQUAT, [pointOf(COMPLETE_SQUAT, STUB_REPS_RESULT)]])]],
    });

    renderHistory();

    expect(await screen.findByText('Could not load your sessions')).toBeDefined();
    expect(screen.getByText('The API answered 500: Database unavailable')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByTestId(`session-${COMPLETE_SQUAT.id}`)).toBeDefined();
    expect(within(card(COMPLETE_SQUAT)).getByText('3 reps')).toBeDefined();
    expect(screen.queryByText('Could not load your sessions')).toBeNull();
    expect(requestsTo(api, SESSIONS_PATH)).toBe(2);
  });

  it('still lists the sessions when their scores could not load', async () => {
    fakeResultsApi({
      '/me': [[200, ME]],
      [SESSIONS_PATH]: [[200, [COMPLETE_SQUAT]]],
      [PROGRESS_PATH]: [[500, { detail: 'Database unavailable' }]],
    });

    renderHistory();

    expect(
      await screen.findByText('Your scores could not load. Open a session to see its result.'),
    ).toBeDefined();
    const squat = within(card(COMPLETE_SQUAT));
    expect(squat.getByText('Complete')).toBeDefined();
    expect(squat.queryByText('3 reps')).toBeNull();
    expect(screen.getByRole('link', { name: /squat/i }).getAttribute('href')).toBe(
      resultPath(COMPLETE_SQUAT.id),
    );
  });
});
