import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, type InitialEntry } from 'react-router-dom';

import PatientPage from './PatientPage';
import { NO_PLAN, PLANK, SQUAT, fakePlanApi, planWith } from './testPlan';

/** Waits a moment, so an update the page has started would show. */
function waitAMoment() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe('PatientPage (My plan)', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function renderPatientPage(initialEntries: InitialEntry[] = ['/patient']) {
    // retry: false, so a failed request fails at once instead of being retried.
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <MantineProvider>
          <MemoryRouter initialEntries={initialEntries}>
            <Routes>
              <Route path="/patient" element={<PatientPage />} />
              <Route path="/patient/upload" element={<div>Upload Page</div>} />
            </Routes>
          </MemoryRouter>
        </MantineProvider>
      </QueryClientProvider>,
    );
  }

  it("shows the exercises of the patient's plan, from GET /plans/me", async () => {
    const api = fakePlanApi([200, planWith(SQUAT, PLANK)]);

    renderPatientPage();

    expect(screen.getByRole('heading', { name: 'My Exercise Plan' })).toBeDefined();
    expect(await screen.findByTestId('exercise-card-squat')).toBeDefined();
    expect(screen.getByTestId('exercise-card-plank')).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Squat' })).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Plank' })).toBeDefined();
    // The illustrations come with the page, by exercise name.
    expect(screen.getByAltText('Illustration showing posture for Squat')).toBeDefined();
    expect(api.mock.calls[0][0]).toBe('http://api.test/plans/me');
  });

  it('shows reps for an exercise done in reps, a hold time for the plank, and times a week', async () => {
    fakePlanApi([200, planWith(SQUAT, PLANK)]);

    renderPatientPage();

    const squat = await screen.findByTestId('exercise-card-squat');
    expect(within(squat).getByText('3 sets × 10 reps')).toBeDefined();
    expect(within(squat).getByText('3 times a week')).toBeDefined();
    const plank = screen.getByTestId('exercise-card-plank');
    expect(within(plank).getByText('3 sets × 30-second hold')).toBeDefined();
    expect(within(plank).getByText('5 times a week')).toBeDefined();
  });

  it("links each Record / Upload button to the upload page with the exercise's plan_exercise_id", async () => {
    fakePlanApi([200, planWith(SQUAT, PLANK)]);

    renderPatientPage();

    const squat = await screen.findByTestId('exercise-card-squat');
    const plank = screen.getByTestId('exercise-card-plank');
    expect(screen.getAllByRole('link', { name: 'Record / Upload' })).toHaveLength(2);
    expect(within(plank).getByRole('link', { name: 'Record / Upload' }).getAttribute('href')).toBe(
      `/patient/upload?plan_exercise_id=${PLANK.id}`,
    );

    const squatUpload = within(squat).getByRole('link', { name: 'Record / Upload' });
    expect(squatUpload.getAttribute('href')).toBe(`/patient/upload?plan_exercise_id=${SQUAT.id}`);
    fireEvent.click(squatUpload);
    expect(await screen.findByText('Upload Page')).toBeDefined();
  });

  it("says so when the therapist hasn't assigned a plan yet (404)", async () => {
    fakePlanApi([404, NO_PLAN]);

    renderPatientPage();

    expect(await screen.findByText("Your therapist hasn't assigned a plan yet")).toBeDefined();
    expect(screen.queryByRole('link', { name: /record \/ upload/i })).toBeNull();
  });

  it('shows a spinner while the plan loads', () => {
    vi.stubGlobal('fetch', () => new Promise(() => {}));

    renderPatientPage();

    expect(screen.getByText('Loading your plan...')).toBeDefined();
    expect(screen.queryByRole('link', { name: /record \/ upload/i })).toBeNull();
  });

  it('shows why the plan could not load, and loads it again on Try again', async () => {
    const api = fakePlanApi([500, { detail: 'Database unavailable' }], [200, planWith(SQUAT)]);

    renderPatientPage();

    expect(await screen.findByText('Could not load your plan')).toBeDefined();
    expect(screen.getByText('The API answered 500: Database unavailable')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByTestId('exercise-card-squat')).toBeDefined();
    expect(api).toHaveBeenCalledTimes(2);
  });

  it('shows no sample data or made-up progress', async () => {
    fakePlanApi([200, planWith(SQUAT, PLANK)]);

    renderPatientPage();
    await screen.findByTestId('exercise-card-squat');

    expect(screen.queryByText('Sample data')).toBeNull();
    expect(screen.queryByText(/progress/i)).toBeNull();
    expect(screen.queryByText(/completed/i)).toBeNull();
    expect(document.querySelector('.mantine-RingProgress-root')).toBeNull();
  });

  it('shows an exercise that has no illustration, such as one added to the library later', async () => {
    const lunge = {
      ...SQUAT,
      exercise: { ...SQUAT.exercise, name: 'lunge', display_name: 'Lunge' },
    };
    fakePlanApi([200, planWith(lunge)]);

    renderPatientPage();

    const card = await screen.findByTestId('exercise-card-lunge');
    expect(within(card).getByRole('heading', { name: 'Lunge' })).toBeDefined();
    expect(within(card).getByText('3 sets × 10 reps')).toBeDefined();
    expect(within(card).queryByRole('img')).toBeNull();
  });

  it('opens a details dialog when a card is clicked, with an upload link for that exercise', async () => {
    fakePlanApi([200, planWith(SQUAT, PLANK)]);

    renderPatientPage();
    fireEvent.click(await screen.findByTestId('exercise-card-squat'));

    // Modal dialog opens covering the page
    const dialog = await screen.findByRole('dialog');
    expect(await screen.findByTestId('expanded-exercise-modal')).toBeDefined();
    expect(screen.getAllByRole('heading', { name: 'Squat' }).length).toBeGreaterThan(0);
    expect(within(dialog).getByText('Target: 3 sets × 10 reps')).toBeDefined();
    expect(within(dialog).getByText('3 times a week')).toBeDefined();
    expect(
      within(dialog).getByRole('link', { name: 'Record / Upload Set' }).getAttribute('href'),
    ).toBe(`/patient/upload?plan_exercise_id=${SQUAT.id}`);

    // Close button dismisses modal
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    await waitFor(() => {
      expect(screen.queryByTestId('expanded-exercise-modal')).toBeNull();
    });
  });

  it('supports expanding card via keyboard navigation (Enter key)', async () => {
    fakePlanApi([200, planWith(SQUAT, PLANK)]);

    renderPatientPage();
    fireEvent.keyDown(await screen.findByTestId('exercise-card-plank'), {
      key: 'Enter',
      code: 'Enter',
    });

    expect(await screen.findByRole('dialog')).toBeDefined();
    expect(screen.getAllByRole('heading', { name: 'Plank' }).length).toBeGreaterThan(0);
  });

  it('leaves Enter on the Record / Upload link to the link, without opening the dialog', async () => {
    fakePlanApi([200, planWith(SQUAT)]);

    renderPatientPage();
    const card = await screen.findByTestId('exercise-card-squat');
    fireEvent.keyDown(within(card).getByRole('link', { name: 'Record / Upload' }), {
      key: 'Enter',
      code: 'Enter',
    });
    await waitAMoment();

    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('provides an accessibility toolbar with text scaling and high contrast toggle', async () => {
    fakePlanApi([200, planWith(SQUAT, PLANK)]);

    renderPatientPage();
    await screen.findByTestId('exercise-card-squat');

    // Accessibility region
    expect(screen.getByRole('region', { name: 'Accessibility options' })).toBeDefined();
    expect(screen.getByLabelText(/adjust text scaling size/i)).toBeDefined();

    // Switch to Large text scale
    const largeOption = screen.getByRole('radio', { name: /^large/i });
    fireEvent.click(largeOption);

    // Toggle High Contrast mode
    const highContrastSwitch = screen.getByRole('switch', {
      name: /toggle high contrast display mode/i,
    });
    expect(highContrastSwitch).toBeDefined();
    fireEvent.click(highContrastSwitch);
  });

  it('shows processing notification when redirected after a session upload', async () => {
    fakePlanApi([200, planWith(SQUAT)]);

    renderPatientPage([
      {
        pathname: '/patient',
        state: { uploadedSessionId: 'sess-987-abc' },
      },
    ]);

    expect(screen.getByText('Upload in Progress')).toBeDefined();
    expect(screen.getByText('sess-987-abc')).toBeDefined();
    expect(screen.getByText('processing')).toBeDefined();
    expect(await screen.findByTestId('exercise-card-squat')).toBeDefined();
  });
});
