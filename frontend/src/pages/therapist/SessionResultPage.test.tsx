import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';

import type { AnalysisResult, LinkedPatientResponse, SessionSummary } from '@/api/model';
import { getListLinkedPatientsQueryKey } from '@/api/patients';
import { getListPatientSessionsQueryKey } from '@/api/results';
import { POLL_INTERVAL_MS } from '@/hooks/useSessionStatus';
import SessionResultPage from './SessionResultPage';
import { patientPath, sessionPath } from './sessionDisplay';
import {
  ANA,
  ANA_LEG_RAISE,
  ANA_PLANK,
  ANA_SESSIONS,
  ANA_SQUAT,
  BEN,
  BEN_PLANK,
  FAILED_NO_PERSON,
  FAILED_TIMED_OUT,
  SIDE_LEG_RAISE_RESULT,
  SQUAT_RESULT,
  STUB_RESULT,
  UNLINKED_PATIENT_ID,
  apiAnswers,
  fakeApi,
  requestsTo,
  withResult,
  type Answer,
} from './testSessions';

const ANA_SESSIONS_PATH = `/patients/${ANA.id}/sessions`;
/** Where each of Ana's sessions has its result. */
const resultPath = (session: SessionSummary) => `/sessions/${session.id}/result`;
/** Ana's leg raise once its analysis has finished. */
const LEG_RAISE_DONE: SessionSummary = { ...ANA_LEG_RAISE, status: 'complete' };

/** Stands in for the patient's detail page (PatientDetailPage), with all their sessions. */
function PatientPage() {
  const { patientId } = useParams();
  return <div>Sessions page for {patientId}</div>;
}

/**
 * Opens the page at this address. `cached` answers are already in the cache, as when the
 * therapist came from the patient's detail page.
 */
function renderPage(
  path = sessionPath(ANA.id, ANA_SQUAT.id),
  { cached }: { cached?: { patients: LinkedPatientResponse[]; sessions: SessionSummary[] } } = {},
) {
  // retry: false, so a failed request fails at once instead of being retried.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (cached) {
    queryClient.setQueryData(getListLinkedPatientsQueryKey(), cached.patients);
    queryClient.setQueryData(getListPatientSessionsQueryKey(ANA.id), cached.sessions);
  }
  render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/therapist" element={<div>Your patients</div>} />
            <Route path="/therapist/patients/:patientId" element={<PatientPage />} />
            <Route
              path="/therapist/patients/:patientId/sessions/:sessionId"
              element={<SessionResultPage />}
            />
          </Routes>
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

/** The big number of the result view: the reps, or the seconds held. */
async function findMainValue(): Promise<string | null> {
  return (await screen.findByTestId('main-value')).textContent;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('SessionResultPage', () => {
  it("shows a complete session's result in the result view", async () => {
    fakeApi(apiAnswers());
    renderPage();

    // Which session this is.
    expect(await screen.findByRole('heading', { name: 'Squat' })).toBeDefined();
    expect(screen.getByText('Complete')).toBeDefined();
    const uploaded = screen.getByText(/^ana@example\.com, uploaded/);
    expect(uploaded.querySelector('time')?.getAttribute('datetime')).toBe(ANA_SQUAT.created_at);

    // Its result, as the result view (SCRUM-59) shows it.
    expect(await findMainValue()).toBe('3');
    expect(screen.getByText('reps')).toBeDefined();
    expect(screen.getByText('Your knees moved inward.')).toBeDefined();
    expect(screen.getByText('Push your knees out so they stay over your toes.')).toBeDefined();
    expect(screen.getByText('Analyzer version 0.1.0.')).toBeDefined();
    // A real result, not a made-up one.
    expect(screen.queryByText('Placeholder result')).toBeNull();
  });

  it("shows another linked patient's result the same way", async () => {
    fakeApi(apiAnswers());
    renderPage(sessionPath(BEN.id, BEN_PLANK.id));

    expect(await screen.findByRole('heading', { name: 'Plank' })).toBeDefined();
    expect(screen.getByText(/^ben@example\.com, uploaded/)).toBeDefined();
    // A plank is held for time.
    expect(await findMainValue()).toBe('22.0');
    expect(screen.getByText('seconds held')).toBeDefined();
  });

  it('says a result the AI service made up is only a placeholder', async () => {
    fakeApi(
      apiAnswers({
        [`GET ${resultPath(ANA_SQUAT)}`]: {
          status: 200,
          body: withResult(ANA_SQUAT, STUB_RESULT),
        },
      }),
    );
    renderPage();

    expect(await screen.findByText('Placeholder result')).toBeDefined();
    expect(screen.getByText(/a made-up example, not taken from the patient's video/)).toBeDefined();
    // The made-up result still shows below the warning.
    expect(await findMainValue()).toBe('3');
    expect(screen.getByText('Analyzer version 0.4.0-stub.')).toBeDefined();
  });

  it.each([
    ['no_person', FAILED_NO_PERSON, /Analyzer version 0\.1\.0\./],
    // A session the backend failed because it was stuck has no analyzer version.
    ['analysis_timed_out', FAILED_TIMED_OUT, null],
  ])(
    'says why a failed session failed, with its error code (%s)',
    async (code, result: AnalysisResult, version) => {
      fakeApi(
        apiAnswers({
          [`GET ${resultPath(ANA_PLANK)}`]: { status: 200, body: withResult(ANA_PLANK, result) },
        }),
      );
      renderPage(sessionPath(ANA.id, ANA_PLANK.id));

      expect(await screen.findByText(result.error_message as string)).toBeDefined();
      expect(screen.getByRole('heading', { name: 'Plank' })).toBeDefined();
      expect(screen.getByText('Failed')).toBeDefined();
      expect(screen.getByText(code).tagName).toBe('CODE');
      if (version) {
        expect(screen.getByText(version)).toBeDefined();
      } else {
        expect(screen.queryByText(/Analyzer version/)).toBeNull();
      }
      // The patient's "Upload again" button isn't the therapist's to press.
      expect(screen.queryByRole('button', { name: 'Upload again' })).toBeNull();
    },
  );

  it("says a processing session is still processing, and shows its result once it's ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const answers = apiAnswers();
    const api = fakeApi(answers);
    renderPage(sessionPath(ANA.id, ANA_LEG_RAISE.id));

    expect(await screen.findByText('Still processing')).toBeDefined();
    expect(screen.getByText('Processing')).toBeDefined();
    expect(requestsTo(api, resultPath(ANA_LEG_RAISE))).toBe(1);

    // Still processing at the next check.
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));
    await vi.waitFor(() => expect(requestsTo(api, resultPath(ANA_LEG_RAISE))).toBe(2));
    expect(screen.getByText('Still processing')).toBeDefined();

    // The analysis finishes before the check after that.
    answers[`GET ${resultPath(ANA_LEG_RAISE)}`] = {
      status: 200,
      body: withResult(LEG_RAISE_DONE, SIDE_LEG_RAISE_RESULT),
    };
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));

    expect(await findMainValue()).toBe('4');
    expect(screen.queryByText('Still processing')).toBeNull();
    // The status is the result's, which is newer than the one in the patient's list.
    expect(screen.getByText('Complete')).toBeDefined();
    expect(screen.queryByText('Processing')).toBeNull();

    // Done, so the page stops asking.
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 5));
    expect(requestsTo(api, resultPath(ANA_LEG_RAISE))).toBe(3);
  });

  it('stops checking after a check fails, says so, and checks again on Try again', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const answers = apiAnswers();
    const api = fakeApi(answers);
    renderPage(sessionPath(ANA.id, ANA_LEG_RAISE.id));
    expect(await screen.findByText('Still processing')).toBeDefined();

    answers[`GET ${resultPath(ANA_LEG_RAISE)}`] = {
      status: 503,
      body: { detail: 'Service Unavailable' },
    };
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));

    expect(await screen.findByText("Couldn't check for the result")).toBeDefined();
    expect(screen.getByText('The API answered 503: Service Unavailable')).toBeDefined();
    // The session still shows as processing, and the page stopped asking.
    expect(screen.getByText('Still processing')).toBeDefined();
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 5));
    expect(requestsTo(api, resultPath(ANA_LEG_RAISE))).toBe(2);

    answers[`GET ${resultPath(ANA_LEG_RAISE)}`] = {
      status: 200,
      body: withResult(LEG_RAISE_DONE, SIDE_LEG_RAISE_RESULT),
    };
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await findMainValue()).toBe('4');
    expect(screen.queryByText("Couldn't check for the result")).toBeNull();
  });

  it.each([
    ["another linked patient's session", BEN_PLANK.id],
    ["a session that doesn't exist", 'c0ffee00-0000-4000-8000-000000000000'],
  ])("says the session isn't found, and asks for no result, for %s", async (_, sessionId) => {
    const api = fakeApi(apiAnswers());
    renderPage(sessionPath(ANA.id, sessionId));

    expect(await screen.findByText('Session not found')).toBeDefined();
    const back = screen.getByRole('link', { name: "See this patient's sessions" });
    expect(back.getAttribute('href')).toBe(patientPath(ANA.id));
    // The API would show Ben's session, but under Ana's name it is never asked for.
    expect(requestsTo(api, `/sessions/${sessionId}/result`)).toBe(0);
    expect(screen.queryByRole('heading', { name: 'Plank' })).toBeNull();
    expect(screen.queryByTestId('main-value')).toBeNull();
  });

  // The API answers 404 for a session the therapist may not see, for example once the
  // patient is unlinked (backend/README.md). A 403 is treated the same.
  it.each([404, 403])(
    "says the session isn't found when the API won't show its result (%s)",
    async (status) => {
      fakeApi(
        apiAnswers({
          [`GET ${resultPath(ANA_SQUAT)}`]: { status, body: { detail: 'Session not found' } },
        }),
      );
      renderPage();

      expect(await screen.findByText('Session not found')).toBeDefined();
      expect(screen.queryByRole('heading', { name: 'Squat' })).toBeNull();
      expect(screen.getByRole('link', { name: "See this patient's sessions" })).toBeDefined();
    },
  );

  it("says the patient isn't found, and asks for nothing of theirs, when the address names someone else", async () => {
    const api = fakeApi(apiAnswers());
    // Ana's session, at an address with someone else's id.
    renderPage(sessionPath(UNLINKED_PATIENT_ID, ANA_SQUAT.id));

    expect(await screen.findByText('Patient not found')).toBeDefined();
    expect(screen.getByRole('link', { name: 'Back to your patients' }).getAttribute('href')).toBe(
      '/therapist',
    );
    expect(requestsTo(api, `/patients/${UNLINKED_PATIENT_ID}/sessions`)).toBe(0);
    expect(requestsTo(api, resultPath(ANA_SQUAT))).toBe(0);
  });

  it.each([404, 403])(
    "says the patient isn't found when the API won't show their sessions (%s)",
    async (status) => {
      const api = fakeApi(
        apiAnswers({
          [`GET ${ANA_SESSIONS_PATH}`]: { status, body: { detail: 'Patient not found' } },
        }),
      );
      renderPage();

      expect(await screen.findByText('Patient not found')).toBeDefined();
      expect(requestsTo(api, resultPath(ANA_SQUAT))).toBe(0);
    },
  );

  it("shows the API's explanation when the result can't load, and tries again", async () => {
    const answers = apiAnswers({
      [`GET ${resultPath(ANA_SQUAT)}`]: {
        status: 500,
        body: { detail: 'Internal Server Error' },
      },
    });
    fakeApi(answers);
    renderPage();

    expect(await screen.findByText("Couldn't load the result")).toBeDefined();
    expect(screen.getByText('The API answered 500: Internal Server Error')).toBeDefined();
    // Which session it is still shows.
    expect(screen.getByRole('heading', { name: 'Squat' })).toBeDefined();

    answers[`GET ${resultPath(ANA_SQUAT)}`] = {
      status: 200,
      body: withResult(ANA_SQUAT, SQUAT_RESULT),
    };
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await findMainValue()).toBe('3');
    expect(screen.queryByText("Couldn't load the result")).toBeNull();
  });

  it("shows the API's explanation when the sessions can't load, and tries again", async () => {
    const answers = apiAnswers({
      [`GET ${ANA_SESSIONS_PATH}`]: { status: 500, body: { detail: 'Internal Server Error' } },
    });
    const api = fakeApi(answers);
    renderPage();

    expect(await screen.findByText("Couldn't load the sessions")).toBeDefined();
    expect(screen.getByText('The API answered 500: Internal Server Error')).toBeDefined();
    expect(requestsTo(api, resultPath(ANA_SQUAT))).toBe(0);

    answers[`GET ${ANA_SESSIONS_PATH}`] = { status: 200, body: ANA_SESSIONS };
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await findMainValue()).toBe('3');
  });

  it('shows which session it is, and a loading message until the result arrives', async () => {
    fakeApi(apiAnswers({ [`GET ${resultPath(ANA_SQUAT)}`]: new Promise(() => {}) }));
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Squat' })).toBeDefined();
    expect(screen.getByText('Loading the result…')).toBeDefined();
  });

  it("waits for the patient's newest sessions before saying a session isn't found", async () => {
    let answerSessions: (answer: Answer) => void = () => {};
    const api = fakeApi(
      apiAnswers({
        [`GET ${ANA_SESSIONS_PATH}`]: new Promise<Answer>((resolve) => {
          answerSessions = resolve;
        }),
      }),
    );
    // The therapist read Ana's list before she uploaded her leg raise.
    renderPage(sessionPath(ANA.id, ANA_LEG_RAISE.id), {
      cached: { patients: [ANA, BEN], sessions: [ANA_SQUAT, ANA_PLANK] },
    });

    // The cached list doesn't have the session, but the page is reading the list again.
    expect(screen.getByText('Loading the session…')).toBeDefined();
    expect(screen.queryByText('Session not found')).toBeNull();
    await vi.waitFor(() => expect(requestsTo(api, ANA_SESSIONS_PATH)).toBe(1));
    expect(screen.queryByText('Session not found')).toBeNull();

    // The new list has it.
    await act(async () => answerSessions({ status: 200, body: ANA_SESSIONS }));
    expect(await screen.findByText('Still processing')).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Side-lying leg raise' })).toBeDefined();
  });

  it('says so if a finished session has no result', async () => {
    fakeApi(
      apiAnswers({
        [`GET ${resultPath(ANA_SQUAT)}`]: { status: 200, body: withResult(ANA_SQUAT, null) },
      }),
    );
    renderPage();

    expect(await screen.findByText('No result was saved for this session.')).toBeDefined();
    expect(screen.queryByText('Still processing')).toBeNull();
  });

  it("links back to all of the patient's sessions", async () => {
    fakeApi(apiAnswers());
    renderPage();

    const back = await screen.findByRole('link', { name: 'Back to all sessions' });
    expect(back.getAttribute('href')).toBe(patientPath(ANA.id));

    fireEvent.click(back);
    expect(await screen.findByText(`Sessions page for ${ANA.id}`)).toBeDefined();
  });
});
