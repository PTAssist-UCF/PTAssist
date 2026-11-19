import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';

import PlansPage from './PlansPage';

const PATIENTS = [
  {
    id: '0b6f3c2e-5d1a-4c8e-9f7b-2a4d6e8c0f13',
    email: 'alex@example.com',
    linked_at: '2026-11-10T12:00:00Z',
  },
  {
    id: '7c2e9a41-3b5d-4f60-8e1a-9d3c5b7f2e04',
    email: 'sam@example.com',
    linked_at: '2026-11-11T08:30:00Z',
  },
];

/** A fake GET /therapist/patients that always gives this answer. */
function fakeApi(status: number, body: unknown) {
  const api = vi.fn<typeof fetch>(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
  );
  vi.stubGlobal('fetch', api);
  return api;
}

/** Stands in for the plan builder, to show which patient it opened. */
function PlanBuilderStub() {
  const { patientId } = useParams();
  return <div>Plan builder for {patientId}</div>;
}

function renderPage() {
  // retry: false, so a failed request fails at once instead of being retried.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter initialEntries={['/therapist/plans']}>
          <Routes>
            <Route path="/therapist/plans" element={<PlansPage />} />
            <Route path="/therapist/patients/:patientId/plan" element={<PlanBuilderStub />} />
            <Route path="/therapist" element={<div>Patient list</div>} />
          </Routes>
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('PlansPage', () => {
  it('lists the linked patients, each linking to their plan builder', async () => {
    const api = fakeApi(200, PATIENTS);
    renderPage();

    expect(screen.getByRole('heading', { name: 'Plan Builder' })).toBeDefined();
    const alex = await screen.findByRole('link', { name: 'alex@example.com' });
    expect(alex.getAttribute('href')).toBe(`/therapist/patients/${PATIENTS[0].id}/plan`);
    const sam = screen.getByRole('link', { name: 'sam@example.com' });
    expect(sam.getAttribute('href')).toBe(`/therapist/patients/${PATIENTS[1].id}/plan`);
    expect(String(api.mock.calls[0][0])).toBe('http://api.test/therapist/patients');
  });

  it("opens a patient's plan builder", async () => {
    fakeApi(200, PATIENTS);
    renderPage();

    fireEvent.click(await screen.findByRole('link', { name: 'sam@example.com' }));

    expect(await screen.findByText(`Plan builder for ${PATIENTS[1].id}`)).toBeDefined();
  });

  it('sends the therapist to the patient list when nobody is linked yet', async () => {
    fakeApi(200, []);
    renderPage();

    expect(await screen.findByText(/You have no linked patients yet/)).toBeDefined();
    fireEvent.click(screen.getByRole('link', { name: 'Patients' }));
    expect(await screen.findByText('Patient list')).toBeDefined();
  });

  it("shows the API's answer when the patients can't load", async () => {
    fakeApi(500, { detail: 'Server error' });
    renderPage();

    expect(await screen.findByText("Couldn't load your patients")).toBeDefined();
    expect(screen.getByText('The API answered 500: Server error')).toBeDefined();
  });

  it('shows a loading message until the patients have loaded', () => {
    vi.stubGlobal('fetch', () => new Promise(() => {}));
    renderPage();

    expect(screen.getByText('Loading your patients…')).toBeDefined();
  });
});
