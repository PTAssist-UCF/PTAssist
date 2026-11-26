import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';

import { getListPatientSessionsQueryKey } from '@/api/results';
import { POLL_INTERVAL_MS } from '@/hooks/useSessionStatus';
import PatientDetailPage from './PatientDetailPage';
import SessionResultPage from './SessionResultPage';
import { patientPath, sessionPath } from './sessionDisplay';
import {
  ANA,
  ANA_LEG_RAISE,
  ANA_PLANK,
  ANA_SESSIONS,
  ANA_SQUAT,
  BEN,
  UNLINKED_PATIENT_ID,
  apiAnswers,
  fakeApi,
  requestsTo,
} from './testSessions';

const ANA_SESSIONS_PATH = `/patients/${ANA.id}/sessions`;

/** Stands in for the patient list (TherapistPage), which links to each patient's page. */
function PatientListPage() {
  return <div>Your patients</div>;
}

/** Stands in for the plan builder (SCRUM-76). */
function PlanPage() {
  const { patientId } = useParams();
  return <div>Plan page for {patientId}</div>;
}

/**
 * Opens the app at this address, with the therapist's pages that this one links to: the
 * session result page is the real one. Returns the query client, to make the page read
 * again.
 */
function renderPage(path = patientPath(ANA.id)) {
  // retry: false, so a failed request fails at once instead of being retried.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/therapist" element={<PatientListPage />} />
            <Route path="/therapist/patients/:patientId" element={<PatientDetailPage />} />
            <Route
              path="/therapist/patients/:patientId/sessions/:sessionId"
              element={<SessionResultPage />}
            />
            <Route path="/therapist/patients/:patientId/plan" element={<PlanPage />} />
          </Routes>
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
  return { queryClient };
}

/** The session rows of the table, newest first (without the header row). */
async function findSessionRows(): Promise<HTMLElement[]> {
  const table = await screen.findByRole('table');
  return within(table).getAllByRole('row').slice(1);
}

/** The text of one column (counted from 0) in each of these rows. */
function column(rows: HTMLElement[], index: number): (string | null)[] {
  return rows.map((row) => within(row).getAllByRole('cell')[index].textContent);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('PatientDetailPage', () => {
  it('shows the patient, and every session they uploaded, newest first, with its status', async () => {
    fakeApi(apiAnswers());
    renderPage();

    expect(await screen.findByRole('heading', { name: 'ana@example.com' })).toBeDefined();
    const linked = screen.getByText(/Linked on/);
    expect(linked.querySelector('time')?.getAttribute('datetime')).toBe(ANA.linked_at);

    const rows = await findSessionRows();
    expect(column(rows, 0)).toEqual(['Side-lying leg raise', 'Squat', 'Plank']);
    expect(column(rows, 2)).toEqual(['Processing', 'Complete', 'Failed']);
    expect(rows.map((row) => row.querySelector('time')?.getAttribute('datetime'))).toEqual(
      ANA_SESSIONS.map((session) => session.created_at),
    );
    // Each row opens that session's result.
    expect(
      rows.map((row) =>
        within(row)
          .getByRole('link', { name: /^Open the / })
          .getAttribute('href'),
      ),
    ).toEqual(ANA_SESSIONS.map((session) => sessionPath(ANA.id, session.id)));
  });

  it.each([
    ['Ana', ANA, 'Squat', '3'],
    ['Ben', BEN, 'Plank', '22.0'],
  ])("opens a session's result from its row (%s)", async (_, patient, exercise, mainValue) => {
    fakeApi(apiAnswers());
    renderPage(patientPath(patient.id));

    fireEvent.click(
      await screen.findByRole('link', { name: new RegExp(`^Open the ${exercise} session from`) }),
    );

    // The session's page, with its result in the result view.
    expect(await screen.findByRole('heading', { name: exercise })).toBeDefined();
    expect((await screen.findByTestId('main-value')).textContent).toBe(mainValue);
    expect(screen.getByText(new RegExp(`^${patient.email}, uploaded`))).toBeDefined();
  });

  it('says so when the patient has no sessions yet', async () => {
    fakeApi(apiAnswers({ [`GET ${ANA_SESSIONS_PATH}`]: { status: 200, body: [] } }));
    renderPage();

    expect(await screen.findByText('No sessions yet')).toBeDefined();
    expect(screen.getByRole('heading', { name: 'ana@example.com' })).toBeDefined();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('shows a loading message until the patient list arrives', () => {
    fakeApi({ 'GET /therapist/patients': new Promise(() => {}) });
    renderPage();

    expect(screen.getByText('Loading the patient…')).toBeDefined();
  });

  it('shows the patient, and a loading message until their sessions arrive', async () => {
    fakeApi(apiAnswers({ [`GET ${ANA_SESSIONS_PATH}`]: new Promise(() => {}) }));
    renderPage();

    expect(await screen.findByRole('heading', { name: 'ana@example.com' })).toBeDefined();
    expect(screen.getByText('Loading the sessions…')).toBeDefined();
  });

  it("shows the API's explanation when the sessions can't load, and tries again", async () => {
    const answers = apiAnswers({
      [`GET ${ANA_SESSIONS_PATH}`]: { status: 500, body: { detail: 'Internal Server Error' } },
    });
    fakeApi(answers);
    renderPage();

    expect(await screen.findByText("Couldn't load the sessions")).toBeDefined();
    expect(screen.getByText('The API answered 500: Internal Server Error')).toBeDefined();

    answers[`GET ${ANA_SESSIONS_PATH}`] = { status: 200, body: ANA_SESSIONS };
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(column(await findSessionRows(), 0)).toEqual(['Side-lying leg raise', 'Squat', 'Plank']);
    expect(screen.queryByText("Couldn't load the sessions")).toBeNull();
  });

  it("shows the API's explanation when the patient list can't load, and asks for no sessions", async () => {
    const api = fakeApi({
      'GET /therapist/patients': { status: 503, body: { detail: 'Could not reach Clerk.' } },
    });
    renderPage();

    expect(await screen.findByText("Couldn't load your patients")).toBeDefined();
    expect(screen.getByText('The API answered 503: Could not reach Clerk.')).toBeDefined();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeDefined();
    expect(requestsTo(api, ANA_SESSIONS_PATH)).toBe(0);
  });

  it("says the patient isn't found, with a way back, when the address names someone else", async () => {
    const api = fakeApi(apiAnswers());
    renderPage(patientPath(UNLINKED_PATIENT_ID));

    expect(await screen.findByText('Patient not found')).toBeDefined();
    expect(
      screen.getByText("You can't see this patient's sessions.", { exact: false }),
    ).toBeDefined();
    // It never asked for that patient's sessions.
    expect(requestsTo(api, `/patients/${UNLINKED_PATIENT_ID}/sessions`)).toBe(0);

    fireEvent.click(screen.getByRole('link', { name: 'Back to your patients' }));
    expect(await screen.findByText('Your patients')).toBeDefined();
  });

  // The API answers 404 for a patient the therapist may no longer see, for example one
  // made a therapist while the link stayed (can_see_patient). A 403 is treated the same.
  it.each([404, 403])(
    "says the patient isn't found when the API won't show their sessions (%s)",
    async (status) => {
      fakeApi(
        apiAnswers({
          [`GET ${ANA_SESSIONS_PATH}`]: { status, body: { detail: 'Patient not found' } },
        }),
      );
      renderPage();

      expect(await screen.findByText('Patient not found')).toBeDefined();
      expect(screen.queryByRole('heading', { name: 'ana@example.com' })).toBeNull();
      expect(screen.getByRole('link', { name: 'Back to your patients' })).toBeDefined();
    },
  );

  it('stops showing the sessions once the API no longer shows them', async () => {
    const answers = apiAnswers();
    fakeApi(answers);
    const { queryClient } = renderPage();
    await findSessionRows();

    // The patient is unlinked elsewhere, then the page reads their sessions again, as when
    // the therapist comes back to the tab.
    answers[`GET ${ANA_SESSIONS_PATH}`] = { status: 404, body: { detail: 'Patient not found' } };
    await act(() =>
      queryClient.refetchQueries({ queryKey: getListPatientSessionsQueryKey(ANA.id) }),
    );

    expect(await screen.findByText('Patient not found')).toBeDefined();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByText('Squat')).toBeNull();
  });

  it('checks again every few seconds while a session is processing, then stops', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const answers = apiAnswers();
    const api = fakeApi(answers);
    renderPage();
    const [newest] = await findSessionRows();
    expect(within(newest).getByText('Processing')).toBeDefined();
    expect(requestsTo(api, ANA_SESSIONS_PATH)).toBe(1);

    // The analysis finishes.
    answers[`GET ${ANA_SESSIONS_PATH}`] = {
      status: 200,
      body: [{ ...ANA_LEG_RAISE, status: 'complete' }, ANA_SQUAT, ANA_PLANK],
    };
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));

    expect(await within(newest).findByText('Complete')).toBeDefined();
    expect(requestsTo(api, ANA_SESSIONS_PATH)).toBe(2);

    // No session is processing any more, so the page stops asking.
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 5));
    expect(requestsTo(api, ANA_SESSIONS_PATH)).toBe(2);
  });

  it("doesn't check again when no session is processing", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    // Ben's only session is complete.
    const api = fakeApi(apiAnswers());
    renderPage(patientPath(BEN.id));
    expect(column(await findSessionRows(), 2)).toEqual(['Complete']);

    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 5));
    expect(requestsTo(api, `/patients/${BEN.id}/sessions`)).toBe(1);
  });

  it("links back to the patient list, and to the patient's plan", async () => {
    fakeApi(apiAnswers());
    renderPage();

    const plan = await screen.findByRole('link', { name: 'Plan for ana@example.com' });
    expect(plan.getAttribute('href')).toBe(`/therapist/patients/${ANA.id}/plan`);
    const back = screen.getByRole('link', { name: 'Back to your patients' });
    expect(back.getAttribute('href')).toBe('/therapist');

    fireEvent.click(plan);
    expect(await screen.findByText(`Plan page for ${ANA.id}`)).toBeDefined();
  });
});
