import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

import { POLL_INTERVAL_MS, POLL_TIMEOUT_MS } from '@/hooks/useSessionStatus';
import SessionResultPage from './SessionResultPage';
import { formatDateTime, resultPath } from './sessionDisplay';
import {
  COMPLETE_PLANK,
  COMPLETE_SQUAT,
  FAILED_SQUAT,
  NO_PERSON_RESULT,
  PROCESSING_SQUAT,
  STUB_HOLD_RESULT,
  STUB_REPS_RESULT,
  ZERO_REPS_RESULT,
  ZERO_REPS_SQUAT,
  advance,
  fakeResultsApi,
  requestsTo,
  resultApiPath,
  statusApiPath,
  statusOf,
  withResult,
} from './testSessions';

describe('SessionResultPage (one result)', () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  /** Opens a session's result page, with stand-ins for the pages it links to. */
  function renderResult(path: string) {
    // retry: false, so a failed request fails at once instead of being retried.
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const router = createMemoryRouter(
      [
        { path: '/patient/history/:sessionId', element: <SessionResultPage /> },
        { path: '/patient/history', element: <div>Results Page</div> },
        { path: '/patient/upload', element: <div>Upload Page</div> },
        { path: '/patient', element: <div>My Plan Page</div> },
      ],
      { initialEntries: [path] },
    );
    render(
      <QueryClientProvider client={queryClient}>
        <MantineProvider>
          <RouterProvider router={router} />
        </MantineProvider>
      </QueryClientProvider>,
    );
    return { router };
  }

  it("shows a complete session's result with ResultView: count, form score, feedback, reps", async () => {
    const api = fakeResultsApi({
      [resultApiPath(COMPLETE_SQUAT)]: [[200, withResult(COMPLETE_SQUAT, STUB_REPS_RESULT)]],
    });

    renderResult(resultPath(COMPLETE_SQUAT.id));

    expect(await screen.findByRole('heading', { name: 'Squat' })).toBeDefined();
    expect(screen.getByText(formatDateTime(COMPLETE_SQUAT.created_at))).toBeDefined();
    expect(screen.getByText('Complete')).toBeDefined();
    expect(screen.getByTestId('main-value').textContent).toBe('3');
    expect(screen.getByText('reps')).toBeDefined();
    expect(screen.getByTestId('form-score').textContent).toBe('97 · Good');
    expect(screen.getByText('Slow down: take at least 2 seconds for each rep.')).toBeDefined();
    expect(screen.getByTestId('rep-2-score').textContent).toBe('90 · Good');
    expect(
      within(screen.getByTestId('rep-2')).getByText('This rep took less than 2 seconds.'),
    ).toBeDefined();
    // A complete session needs no polling.
    expect(requestsTo(api, statusApiPath(COMPLETE_SQUAT))).toBe(0);
  });

  it("shows a plank's hold time, not reps", async () => {
    fakeResultsApi({
      [resultApiPath(COMPLETE_PLANK)]: [[200, withResult(COMPLETE_PLANK, STUB_HOLD_RESULT)]],
    });

    renderResult(resultPath(COMPLETE_PLANK.id));

    expect(await screen.findByRole('heading', { name: 'Plank' })).toBeDefined();
    expect(screen.getByTestId('main-value').textContent).toBe('22.0');
    expect(screen.getByText('seconds held')).toBeDefined();
    expect(screen.getByTestId('form-score').textContent).toBe('77 · Fair');
    expect(screen.getByText('Holds')).toBeDefined();
  });

  it('shows 0 reps and no form score when no rep was seen', async () => {
    fakeResultsApi({
      [resultApiPath(ZERO_REPS_SQUAT)]: [[200, withResult(ZERO_REPS_SQUAT, ZERO_REPS_RESULT)]],
    });

    renderResult(resultPath(ZERO_REPS_SQUAT.id));

    expect(await screen.findByTestId('main-value')).toBeDefined();
    expect(screen.getByTestId('main-value').textContent).toBe('0');
    expect(screen.queryByTestId('form-score')).toBeNull();
    expect(screen.getByText(ZERO_REPS_RESULT.feedback[0])).toBeDefined();
  });

  it('shows why the analysis failed, and Upload again opens the upload page for that exercise', async () => {
    fakeResultsApi({
      [resultApiPath(FAILED_SQUAT)]: [[200, withResult(FAILED_SQUAT, NO_PERSON_RESULT)]],
    });
    const { router } = renderResult(resultPath(FAILED_SQUAT.id));

    const failed = await screen.findByTestId('result-failed');
    expect(screen.getByText('Failed')).toBeDefined();
    expect(within(failed).getByText(NO_PERSON_RESULT.error_message!)).toBeDefined();

    fireEvent.click(within(failed).getByRole('button', { name: 'Upload again' }));

    expect(await screen.findByText('Upload Page')).toBeDefined();
    expect(router.state.location.pathname).toBe('/patient/upload');
    expect(router.state.location.search).toBe(`?plan_exercise_id=${FAILED_SQUAT.plan_exercise_id}`);
  });

  it('offers no re-upload when the exercise has no analyzer (unknown_exercise)', async () => {
    const unknownExercise = {
      ...NO_PERSON_RESULT,
      error_code: 'unknown_exercise' as const,
      error_message: "We can't analyze this exercise yet.",
    };
    fakeResultsApi({
      [resultApiPath(FAILED_SQUAT)]: [[200, withResult(FAILED_SQUAT, unknownExercise)]],
    });

    renderResult(resultPath(FAILED_SQUAT.id));

    const failed = await screen.findByTestId('result-failed');
    expect(within(failed).getByText("We can't analyze this exercise yet.")).toBeDefined();
    expect(within(failed).queryByRole('button', { name: 'Upload again' })).toBeNull();
  });

  it.each([
    ['another patient', resultPath(COMPLETE_SQUAT.id), 404],
    ['an id that is not a session id', resultPath('not-a-session'), 422],
  ])("says the session wasn't found for %s (%i)", async (_case, path, status) => {
    const apiPath = `/sessions/${path.split('/').pop()}/result`;
    fakeResultsApi({ [apiPath]: [[status, { detail: 'Session not found' }]] });

    renderResult(path);

    expect(await screen.findByText('Session not found')).toBeDefined();
    const allResults = screen.getByRole('link', { name: 'See all your results' });
    expect(allResults.getAttribute('href')).toBe('/patient/history');
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
  });

  it('shows why the result could not load, and loads it again on Try again', async () => {
    const api = fakeResultsApi({
      [resultApiPath(COMPLETE_SQUAT)]: [
        [500, { detail: 'Database unavailable' }],
        [200, withResult(COMPLETE_SQUAT, STUB_REPS_RESULT)],
      ],
    });

    renderResult(resultPath(COMPLETE_SQUAT.id));

    expect(await screen.findByText('Could not load this result')).toBeDefined();
    expect(screen.getByText('The API answered 500: Database unavailable')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByTestId('main-value')).toBeDefined();
    expect(screen.getByTestId('main-value').textContent).toBe('3');
    expect(requestsTo(api, resultApiPath(COMPLETE_SQUAT))).toBe(2);
  });

  it('links back to all results and to My Plan', async () => {
    fakeResultsApi({
      [resultApiPath(COMPLETE_SQUAT)]: [[200, withResult(COMPLETE_SQUAT, STUB_REPS_RESULT)]],
    });

    renderResult(resultPath(COMPLETE_SQUAT.id));
    await screen.findByTestId('main-value');

    expect(screen.getByRole('link', { name: 'Back to Plan' }).getAttribute('href')).toBe(
      '/patient',
    );
    fireEvent.click(screen.getByRole('link', { name: 'All results' }));
    expect(await screen.findByText('Results Page')).toBeDefined();
  });

  it('polls a processing session, and shows its result once the analysis has finished', async () => {
    vi.useFakeTimers();
    const api = fakeResultsApi({
      // null while processing. Loaded again once the poll says the analysis has finished.
      [resultApiPath(PROCESSING_SQUAT)]: [
        [200, withResult(PROCESSING_SQUAT, null)],
        [200, withResult(PROCESSING_SQUAT, STUB_REPS_RESULT)],
      ],
      [statusApiPath(PROCESSING_SQUAT)]: [
        [200, statusOf(PROCESSING_SQUAT, 'processing')],
        [200, statusOf(PROCESSING_SQUAT, 'complete')],
      ],
    });

    renderResult(resultPath(PROCESSING_SQUAT.id));
    await advance(0);

    expect(screen.getByText('Analyzing your video...')).toBeDefined();
    expect(screen.getByText('Processing')).toBeDefined();
    expect(screen.queryByTestId('main-value')).toBeNull();
    expect(requestsTo(api, statusApiPath(PROCESSING_SQUAT))).toBe(1);

    await advance(POLL_INTERVAL_MS);

    expect(screen.getByTestId('main-value').textContent).toBe('3');
    expect(screen.getByTestId('form-score').textContent).toBe('97 · Good');
    expect(screen.getByText('Complete')).toBeDefined();
    expect(screen.queryByText('Analyzing your video...')).toBeNull();
    expect(requestsTo(api, resultApiPath(PROCESSING_SQUAT))).toBe(2);

    // Done: no more polling.
    await advance(POLL_INTERVAL_MS * 5);
    expect(requestsTo(api, statusApiPath(PROCESSING_SQUAT))).toBe(2);
  });

  it('shows a failure that the poll finds, with Upload again', async () => {
    vi.useFakeTimers();
    fakeResultsApi({
      [resultApiPath(PROCESSING_SQUAT)]: [
        [200, withResult(PROCESSING_SQUAT, null)],
        [200, withResult(PROCESSING_SQUAT, NO_PERSON_RESULT)],
      ],
      [statusApiPath(PROCESSING_SQUAT)]: [
        [200, statusOf(PROCESSING_SQUAT, 'processing')],
        [200, statusOf(PROCESSING_SQUAT, 'failed')],
      ],
    });

    renderResult(resultPath(PROCESSING_SQUAT.id));
    await advance(0);
    await advance(POLL_INTERVAL_MS);

    const failed = screen.getByTestId('result-failed');
    expect(within(failed).getByText(NO_PERSON_RESULT.error_message!)).toBeDefined();
    expect(within(failed).getByRole('button', { name: 'Upload again' })).toBeDefined();
    expect(screen.getByText('Failed')).toBeDefined();
  });

  it('says so when the analysis takes too long, and checks again on Check again', async () => {
    vi.useFakeTimers();
    // The answers can change during the test: a request gets the last answer on its list.
    const resultAnswers: [number, unknown][] = [[200, withResult(PROCESSING_SQUAT, null)]];
    const statusAnswers: [number, unknown][] = [[200, statusOf(PROCESSING_SQUAT, 'processing')]];
    const api = fakeResultsApi({
      [resultApiPath(PROCESSING_SQUAT)]: resultAnswers,
      [statusApiPath(PROCESSING_SQUAT)]: statusAnswers,
    });

    renderResult(resultPath(PROCESSING_SQUAT.id));
    await advance(0);
    await advance(POLL_TIMEOUT_MS + POLL_INTERVAL_MS);

    expect(screen.getByText('This is taking longer than usual')).toBeDefined();
    const polls = requestsTo(api, statusApiPath(PROCESSING_SQUAT));
    await advance(POLL_INTERVAL_MS * 5);
    // The polling has stopped.
    expect(requestsTo(api, statusApiPath(PROCESSING_SQUAT))).toBe(polls);

    // The analysis finishes later.
    statusAnswers.push([200, statusOf(PROCESSING_SQUAT, 'complete')]);
    resultAnswers.push([200, withResult(PROCESSING_SQUAT, STUB_REPS_RESULT)]);
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }));
    await advance(0);

    expect(requestsTo(api, statusApiPath(PROCESSING_SQUAT))).toBe(polls + 1);
    expect(screen.getByTestId('main-value').textContent).toBe('3');
    expect(screen.queryByText('This is taking longer than usual')).toBeNull();
  });

  it('says so when the poll fails, and starts it again on Try again', async () => {
    vi.useFakeTimers();
    fakeResultsApi({
      [resultApiPath(PROCESSING_SQUAT)]: [
        [200, withResult(PROCESSING_SQUAT, null)],
        [200, withResult(PROCESSING_SQUAT, STUB_REPS_RESULT)],
      ],
      [statusApiPath(PROCESSING_SQUAT)]: [
        [503, { detail: 'Service unavailable' }],
        [200, statusOf(PROCESSING_SQUAT, 'complete')],
      ],
    });

    renderResult(resultPath(PROCESSING_SQUAT.id));
    await advance(0);

    expect(screen.getByText('Could not check on your video')).toBeDefined();
    expect(screen.getByText('The API answered 503: Service unavailable')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await advance(0);

    expect(screen.getByTestId('main-value').textContent).toBe('3');
  });
});
