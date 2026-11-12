import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';

import type { LinkedPatientResponse, SessionStatus, SessionSummary } from '@/api/model';
import { getListPatientSessionsQueryKey } from '@/api/results';
import TherapistPage from './TherapistPage';

// Synthetic patients, in the order the API lists them (by email).
const ANA: LinkedPatientResponse = {
  id: '0b6f3c2e-1a4d-4c8e-9f21-5d7a8b9c0e11',
  email: 'ana@example.com',
  linked_at: '2026-11-01T15:00:00Z',
};
const BEN: LinkedPatientResponse = {
  id: '1c7a4d3f-2b5e-4d9f-8a32-6e8b9c0d1f22',
  email: 'ben@example.com',
  linked_at: '2026-11-02T15:00:00Z',
};
const CAL: LinkedPatientResponse = {
  id: '2d8b5e4a-3c6f-4e0a-9b43-7f9c0d1e2a33',
  email: 'cal@example.com',
  linked_at: '2026-11-03T15:00:00Z',
};
const DEE: LinkedPatientResponse = {
  id: '3e9c6f5b-4d7a-4f1b-8c54-8a0d1e2f3b44',
  email: 'dee@example.com',
  linked_at: '2026-11-04T15:00:00Z',
};
// The id the fake API gives a newly linked patient.
const NEW_PATIENT_ID = '4f0d7a6c-5e8b-4a2c-9d65-9b1e2f3a4c55';

// The API's own sentences for each linking error (backend/app/routes/therapist_patients.py).
const NO_PATIENT =
  'No patient uses that email. They need to sign in to PTAssist once before you can link them.';
const ALREADY_LINKED = 'That patient is already linked to you';
const SHARED_EMAIL =
  "More than one patient uses that email, so it can't be linked. Ask the team to check it.";
const NOT_A_THERAPIST = 'Only therapists can do this';

/** A session in a patient's list, as the API sends it. */
function session(status: SessionStatus, createdAt: string, exercise = 'Squat'): SessionSummary {
  return {
    id: `session-${createdAt}`,
    plan_exercise_id: 'plan-exercise-1',
    exercise_name: exercise.toLowerCase().replaceAll(' ', '_'),
    exercise_display_name: exercise,
    status,
    created_at: createdAt,
  };
}

/** The fake API's answer to one request: a status and a JSON body (none for 204). */
type Answer = { status: number; body?: unknown };

/**
 * Replaces fetch with a fake API, so the page's real hooks run with no backend. `answer`
 * gets each request's method, path, and JSON body, and can take its time (return a
 * promise); if it throws, the request fails as if the API couldn't be reached. Returns the
 * fake, to check which requests were sent.
 */
function fakeApi(
  answer: (method: string, path: string, body: unknown) => Answer | Promise<Answer>,
) {
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
    const { pathname } = new URL(String(input));
    const requestBody = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    const { status, body } = await answer(init?.method ?? 'GET', pathname, requestBody);
    return new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

/** Answers the page's reads: the patient list, and each patient's sessions (newest first). */
function answerReads(
  method: string,
  path: string,
  patients: LinkedPatientResponse[],
  sessions: Record<string, SessionSummary[]> = {},
): Answer {
  if (method === 'GET' && path === '/therapist/patients') {
    return { status: 200, body: patients };
  }
  const patientId = path.match(/^\/patients\/([^/]+)\/sessions$/)?.[1];
  if (method === 'GET' && patientId) {
    return { status: 200, body: sessions[patientId] ?? [] };
  }
  return { status: 404, body: { detail: 'Not Found' } };
}

/**
 * A fake API where linking works the way the real one does: it lowercases the email and
 * adds the patient, so the next GET /therapist/patients lists them.
 */
function apiThatLinks(linked: LinkedPatientResponse[]) {
  return fakeApi((method, path, body) => {
    if (method === 'POST' && path === '/therapist/patients') {
      const email = (body as { email: string }).email.trim().toLowerCase();
      const patient = { id: NEW_PATIENT_ID, email, linked_at: '2026-11-12T15:00:00Z' };
      linked.push(patient);
      return { status: 201, body: patient };
    }
    return answerReads(method, path, linked);
  });
}

/** The requests the page sent with this method to this path. */
function requests(api: ReturnType<typeof fakeApi>, method: string, path: string) {
  return api.mock.calls.filter(
    ([input, init]) =>
      (init?.method ?? 'GET') === method && new URL(String(input)).pathname === path,
  );
}

/** Stands in for the plan builder (SCRUM-76) that each row links to. */
function PlanPage() {
  const { patientId } = useParams();
  return <div>Plan page for {patientId}</div>;
}

/**
 * Opens the page at /therapist, wrapped the way main.tsx and App.tsx wrap it. Returns the
 * page's query client, to make it read again.
 */
function renderPage() {
  // retry: false, so a failed request fails at once instead of being retried.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter initialEntries={['/therapist']}>
          <Routes>
            <Route path="/therapist" element={<TherapistPage />} />
            <Route path="/therapist/patients/:patientId/plan" element={<PlanPage />} />
          </Routes>
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
  return { queryClient };
}

/** Waits a moment, so an answer the fake API just sent reaches the page. */
function waitAMoment() {
  return act(() => new Promise((resolve) => setTimeout(resolve, 20)));
}

/** The table row of the patient with this email. */
async function findRow(email: string): Promise<HTMLElement> {
  const cell = await screen.findByText(email);
  return cell.closest('tr') as HTMLElement;
}

/** Opens the link dialog with the "+ Link New Patient" button. */
async function openLinkDialog(): Promise<HTMLElement> {
  fireEvent.click(screen.getByRole('button', { name: '+ Link New Patient' }));
  return screen.findByRole('dialog', { name: 'Link a patient' });
}

/** Types this email in the link dialog and sends it. */
function submitEmail(dialog: HTMLElement, email: string) {
  fireEvent.change(within(dialog).getByLabelText("Patient's email"), {
    target: { value: email },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Link patient' }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('patient list', () => {
  it('lists linked patients with the status, exercise, and time of their last session', async () => {
    fakeApi((method, path) =>
      answerReads(method, path, [ANA, BEN, CAL, DEE], {
        [ANA.id]: [
          session('complete', '2026-11-10T15:00:00Z'),
          session('failed', '2026-11-09T15:00:00Z'),
        ],
        [BEN.id]: [session('processing', '2026-11-11T15:00:00Z', 'Plank')],
        [CAL.id]: [session('failed', '2026-11-08T15:00:00Z', 'Side leg raise')],
        // DEE has no sessions.
      }),
    );

    renderPage();

    const ana = await findRow('ana@example.com');
    expect(await within(ana).findByText('Complete')).toBeDefined();
    expect(within(ana).getByText('Squat')).toBeDefined();
    expect(ana.querySelector('time')?.getAttribute('datetime')).toBe('2026-11-10T15:00:00Z');
    // Only the newest session counts.
    expect(within(ana).queryByText('Failed')).toBeNull();

    const ben = await findRow('ben@example.com');
    expect(await within(ben).findByText('Processing')).toBeDefined();
    expect(within(ben).getByText('Plank')).toBeDefined();

    const cal = await findRow('cal@example.com');
    expect(await within(cal).findByText('Failed')).toBeDefined();
    expect(within(cal).getByText('Side leg raise')).toBeDefined();

    const dee = await findRow('dee@example.com');
    expect(await within(dee).findByText('No sessions yet')).toBeDefined();
    expect(dee.querySelector('time')).toBeNull();
  });

  it('says so when no patient is linked yet', async () => {
    fakeApi((method, path) => answerReads(method, path, []));

    renderPage();

    expect(await screen.findByText('No linked patients yet')).toBeDefined();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('shows the heading, the link button, and a loading message until the list arrives', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => new Promise<Response>(() => {})),
    );

    renderPage();

    expect(screen.getByText('Assigned Patients')).toBeDefined();
    expect(screen.getByRole('button', { name: '+ Link New Patient' })).toBeDefined();
    expect(screen.getByText('Loading your patients…')).toBeDefined();
  });

  it("shows the API's explanation when the list can't load", async () => {
    fakeApi(() => ({ status: 503, body: { detail: 'Could not reach Clerk. Try again.' } }));

    renderPage();

    expect(await screen.findByText('Could not load your patients')).toBeDefined();
    expect(screen.getByText('Could not reach Clerk. Try again.')).toBeDefined();
  });

  it("says so in the row when a patient's sessions can't load", async () => {
    fakeApi((method, path) =>
      path.endsWith('/sessions')
        ? { status: 500, body: { detail: 'Internal Server Error' } }
        : answerReads(method, path, [ANA]),
    );

    renderPage();

    const ana = await findRow('ana@example.com');
    expect(await within(ana).findByText("Couldn't load sessions")).toBeDefined();
  });

  // The API answers 404 for a patient the caller may no longer see, for example a patient
  // made a therapist while the link stayed (can_see_patient). A 403 is treated the same.
  it.each([404, 403])(
    'stops showing the last session once the API denies access to it (%s)',
    async (status) => {
      let denied = false;
      fakeApi((method, path) =>
        denied && path === `/patients/${ANA.id}/sessions`
          ? { status, body: { detail: 'Patient not found' } }
          : answerReads(method, path, [ANA], {
              [ANA.id]: [session('complete', '2026-11-10T15:00:00Z')],
            }),
      );
      const { queryClient } = renderPage();
      const ana = await findRow('ana@example.com');
      expect(await within(ana).findByText('Complete')).toBeDefined();

      // The page reads the sessions again, as when the therapist comes back to the tab.
      denied = true;
      await act(() =>
        queryClient.refetchQueries({ queryKey: getListPatientSessionsQueryKey(ANA.id) }),
      );

      expect(await within(ana).findByText('Sessions not available')).toBeDefined();
      expect(within(ana).queryByText('Complete')).toBeNull();
      expect(within(ana).queryByText('Squat')).toBeNull();
      expect(ana.querySelector('time')).toBeNull();
    },
  );

  it("links each patient to their plan page, at the plan builder's address", async () => {
    fakeApi((method, path) => answerReads(method, path, [ANA]));
    renderPage();

    const ana = await findRow('ana@example.com');
    const plan = within(ana).getByRole('link', { name: 'Plan for ana@example.com' });
    expect(plan.getAttribute('href')).toBe(`/therapist/patients/${ANA.id}/plan`);

    fireEvent.click(plan);

    expect(await screen.findByText(`Plan page for ${ANA.id}`)).toBeDefined();
  });
});

describe('linking a patient', () => {
  it('links a patient by email, then shows them in the refreshed list', async () => {
    const api = apiThatLinks([ANA]);
    renderPage();
    await findRow('ana@example.com');

    const dialog = await openLinkDialog();
    submitEmail(dialog, '  New.Patient@Example.com ');

    // The new patient shows up in the list, which was loaded again after the link.
    expect(await findRow('new.patient@example.com')).toBeDefined();
    expect(screen.getByText('Linked new.patient@example.com.')).toBeDefined();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(requests(api, 'GET', '/therapist/patients')).toHaveLength(2);
    // The email went out without the spaces around it.
    const [[, post]] = requests(api, 'POST', '/therapist/patients');
    expect(JSON.parse(post?.body as string)).toEqual({ email: 'New.Patient@Example.com' });
  });

  it('shows the new patient when the link is answered before the list first loads', async () => {
    const linked = [ANA];
    let listReads = 0;
    let releaseFirstRead = () => {};
    const firstReadHeld = new Promise<void>((resolve) => {
      releaseFirstRead = resolve;
    });
    let firstReadAnswered = false;
    fakeApi(async (method, path, body) => {
      if (method === 'GET' && path === '/therapist/patients') {
        listReads += 1;
        // A read answers with the list as it was when the read arrived.
        const patients = [...linked];
        if (listReads === 1) {
          // The first read is slow: it arrived before the link, and answers after it.
          await firstReadHeld;
          firstReadAnswered = true;
        }
        return { status: 200, body: patients };
      }
      if (method === 'POST' && path === '/therapist/patients') {
        const { email } = body as { email: string };
        const patient = { id: NEW_PATIENT_ID, email, linked_at: '2026-11-12T15:00:00Z' };
        linked.push(patient);
        // The slow first read answers a moment after the page gets this answer.
        setTimeout(releaseFirstRead, 50);
        return { status: 201, body: patient };
      }
      return answerReads(method, path, linked);
    });
    renderPage();

    // The link button works while the list is still loading.
    expect(screen.getByText('Loading your patients…')).toBeDefined();
    const dialog = await openLinkDialog();
    submitEmail(dialog, 'new.patient@example.com');

    expect(await screen.findByText('Linked new.patient@example.com.')).toBeDefined();
    // The slow first read has answered too, with the list from before the link. The page
    // must not show that one.
    await waitFor(() => expect(firstReadAnswered).toBe(true));
    await waitAMoment();
    expect(screen.getByText('new.patient@example.com')).toBeDefined();
    expect(screen.getByText('ana@example.com')).toBeDefined();
  });

  it('asks for an email before sending anything, and clears that once one is typed', async () => {
    const api = apiThatLinks([]);
    renderPage();
    await screen.findByText('No linked patients yet');

    const dialog = await openLinkDialog();
    submitEmail(dialog, '   ');

    expect(await within(dialog).findByText("Enter the patient's email.")).toBeDefined();
    expect(requests(api, 'POST', '/therapist/patients')).toHaveLength(0);

    fireEvent.change(within(dialog).getByLabelText("Patient's email"), {
      target: { value: 'ana@example.com' },
    });
    expect(within(dialog).queryByText("Enter the patient's email.")).toBeNull();
  });

  it.each([
    ['no patient uses the email', 404, { detail: NO_PATIENT }, NO_PATIENT],
    ['the patient is already linked', 409, { detail: ALREADY_LINKED }, ALREADY_LINKED],
    ['more than one patient uses the email', 409, { detail: SHARED_EMAIL }, SHARED_EMAIL],
    [
      'the API refuses the email (422)',
      422,
      {
        detail: [
          {
            type: 'string_too_long',
            loc: ['body', 'email'],
            msg: 'String should have at most 320 characters',
          },
        ],
      },
      'Check the email address and try again.',
    ],
    ['the caller is not a therapist', 403, { detail: NOT_A_THERAPIST }, NOT_A_THERAPIST],
  ])('says so when %s, and keeps the dialog open', async (_, status, body, message) => {
    const api = fakeApi((method, path) =>
      method === 'POST' ? { status, body } : answerReads(method, path, [ANA]),
    );
    renderPage();
    await findRow('ana@example.com');

    const dialog = await openLinkDialog();
    submitEmail(dialog, 'someone@example.com');

    expect(await within(dialog).findByText(message)).toBeDefined();
    expect(screen.getByRole('dialog', { name: 'Link a patient' })).toBeDefined();
    // Nothing changed, so the list isn't loaded again.
    expect(requests(api, 'GET', '/therapist/patients')).toHaveLength(1);
  });

  it('says so when the API cannot be reached', async () => {
    fakeApi((method, path) => {
      if (method === 'POST') {
        // What fetch does when the API is down or the browser blocks the answer (CORS).
        throw new TypeError('Failed to fetch');
      }
      return answerReads(method, path, [ANA]);
    });
    renderPage();
    await findRow('ana@example.com');

    const dialog = await openLinkDialog();
    submitEmail(dialog, 'someone@example.com');

    expect(
      await within(dialog).findByText(
        'Could not reach the API. Check your connection and try again.',
      ),
    ).toBeDefined();
  });

  it('starts with an empty form each time the dialog opens', async () => {
    fakeApi((method, path) =>
      method === 'POST'
        ? { status: 404, body: { detail: NO_PATIENT } }
        : answerReads(method, path, [ANA]),
    );
    renderPage();
    await findRow('ana@example.com');

    let dialog = await openLinkDialog();
    submitEmail(dialog, 'someone@example.com');
    await within(dialog).findByText(NO_PATIENT);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    dialog = await openLinkDialog();
    const input = within(dialog).getByLabelText("Patient's email") as HTMLInputElement;
    expect(input.value).toBe('');
    expect(within(dialog).queryByText(NO_PATIENT)).toBeNull();
  });
});

describe('unlinking a patient', () => {
  it('asks first, then unlinks the patient and refreshes the list', async () => {
    let linked = [ANA, BEN];
    const api = fakeApi((method, path) => {
      if (method === 'DELETE' && path === `/therapist/patients/${ANA.id}`) {
        linked = linked.filter((patient) => patient.id !== ANA.id);
        return { status: 204 };
      }
      return answerReads(method, path, linked);
    });
    renderPage();
    const ana = await findRow('ana@example.com');

    // Cancel: nothing is sent.
    fireEvent.click(within(ana).getByRole('button', { name: 'Unlink ana@example.com' }));
    let dialog = await screen.findByRole('dialog', { name: 'Unlink patient?' });
    expect(within(dialog).getByText('ana@example.com')).toBeDefined();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(requests(api, 'DELETE', `/therapist/patients/${ANA.id}`)).toHaveLength(0);

    // Confirm: the patient is unlinked and leaves the list.
    fireEvent.click(within(ana).getByRole('button', { name: 'Unlink ana@example.com' }));
    dialog = await screen.findByRole('dialog', { name: 'Unlink patient?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Unlink' }));

    await waitFor(() => expect(screen.queryByText('ana@example.com')).toBeNull());
    expect(screen.getByText('Unlinked ana@example.com.')).toBeDefined();
    expect(screen.getByText('ben@example.com')).toBeDefined();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(requests(api, 'DELETE', `/therapist/patients/${ANA.id}`)).toHaveLength(1);
  });

  it('takes the patient and their last session off the page even if the list then fails to load', async () => {
    let unlinked = false;
    const api = fakeApi((method, path) => {
      if (method === 'DELETE' && path === `/therapist/patients/${ANA.id}`) {
        unlinked = true;
        return { status: 204 };
      }
      // Loading the list again fails, so only the page itself can take Ana off it.
      if (unlinked && path === '/therapist/patients') {
        return { status: 500, body: { detail: 'Internal Server Error' } };
      }
      return answerReads(method, path, [ANA, BEN], {
        [ANA.id]: [session('complete', '2026-11-10T15:00:00Z')],
      });
    });
    renderPage();
    const ana = await findRow('ana@example.com');
    await within(ana).findByText('Complete');

    fireEvent.click(within(ana).getByRole('button', { name: 'Unlink ana@example.com' }));
    const dialog = await screen.findByRole('dialog', { name: 'Unlink patient?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Unlink' }));

    expect(await screen.findByText('Unlinked ana@example.com.')).toBeDefined();
    // The page asked for the list again, and that failed.
    await waitFor(() => expect(requests(api, 'GET', '/therapist/patients')).toHaveLength(2));
    await waitAMoment();
    // Ana's row, with her last session, is gone; Ben's stays.
    expect(ana.isConnected).toBe(false);
    expect(screen.queryByText('Complete')).toBeNull();
    expect(screen.getByText('ben@example.com')).toBeDefined();
  });

  it('says so when the patient was already unlinked, and takes them off the list', async () => {
    let deleteAnswered = false;
    const api = fakeApi((method, path) => {
      if (method === 'DELETE') {
        deleteAnswered = true;
        return { status: 404, body: { detail: 'Patient not found' } };
      }
      // Loading the list again fails, so only the page itself can take Ana off it.
      if (deleteAnswered && path === '/therapist/patients') {
        return { status: 500, body: { detail: 'Internal Server Error' } };
      }
      return answerReads(method, path, [ANA, BEN]);
    });
    renderPage();
    const ana = await findRow('ana@example.com');

    fireEvent.click(within(ana).getByRole('button', { name: 'Unlink ana@example.com' }));
    const dialog = await screen.findByRole('dialog', { name: 'Unlink patient?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Unlink' }));

    expect(
      await within(dialog).findByText('This patient is no longer linked to you.'),
    ).toBeDefined();
    await waitFor(() => expect(requests(api, 'GET', '/therapist/patients')).toHaveLength(2));
    await waitAMoment();
    // Ana's row is gone (the dialog, still open, names her); Ben's stays.
    expect(ana.isConnected).toBe(false);
    expect(screen.getByText('ben@example.com')).toBeDefined();
  });
});
