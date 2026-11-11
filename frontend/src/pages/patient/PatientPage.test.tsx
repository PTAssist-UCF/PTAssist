import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { MemoryRouter, Route, Routes, type InitialEntry } from 'react-router-dom';

import PatientPage from './PatientPage';
import { MOCK_ASSIGNED_EXERCISES } from './mockExercises';

describe('PatientPage Dashboard', () => {
  afterEach(() => {
    cleanup();
  });

  function renderPatientPage(initialEntries: InitialEntry[] = ['/patient']) {
    return render(
      <MantineProvider>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path="/patient" element={<PatientPage />} />
            <Route path="/patient/upload" element={<div>Upload Page</div>} />
          </Routes>
        </MemoryRouter>
      </MantineProvider>,
    );
  }

  it('renders the dashboard heading and all 5 assigned exercise cards', () => {
    renderPatientPage();

    expect(screen.getByRole('heading', { name: 'My Exercise Plan' })).toBeDefined();

    for (const exercise of MOCK_ASSIGNED_EXERCISES) {
      expect(screen.getByTestId(`exercise-card-${exercise.name}`)).toBeDefined();
      expect(screen.getByRole('heading', { name: exercise.displayName })).toBeDefined();
    }
  });

  it('each card contains exercise name, image, pie chart (ring progress), and written description', () => {
    renderPatientPage();

    for (const exercise of MOCK_ASSIGNED_EXERCISES) {
      const card = screen.getByTestId(`exercise-card-${exercise.name}`);

      // Exercise name
      expect(card.textContent).toContain(exercise.displayName);

      // Target description
      expect(card.textContent).toContain(exercise.targetDescription);

      // Image with alt text
      const img = screen.getByAltText(
        `Illustration showing posture for ${exercise.displayName}`,
      ) as HTMLImageElement;
      expect(img).toBeDefined();
      expect(img.src).toContain('data:image/svg+xml');

      // Pie chart / Ring progress
      const ring = screen.getByLabelText(new RegExp(`${exercise.displayName} progress pie chart`));
      expect(ring).toBeDefined();
      expect(card.textContent).toContain(`${exercise.progressPercent}%`);

      // Written description of progress
      expect(card.textContent).toContain(exercise.progressDescription);
    }
  });

  it('opens an expanded card modal when a card is clicked, greying out background', async () => {
    renderPatientPage();

    const squatCard = screen.getByTestId('exercise-card-squat');
    fireEvent.click(squatCard);

    // Modal dialog opens covering the page
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeDefined();
    expect(await screen.findByTestId('expanded-exercise-modal')).toBeDefined();
    expect(screen.getAllByRole('heading', { name: 'Squat' }).length).toBeGreaterThan(0);
    expect(screen.getByText('Daily Progress Summary')).toBeDefined();

    // Close button dismisses modal
    const closeButton = screen.getByRole('button', { name: 'Close' });
    fireEvent.click(closeButton);

    await waitFor(() => {
      expect(screen.queryByTestId('expanded-exercise-modal')).toBeNull();
    });
  });

  it('supports expanding card via keyboard navigation (Enter key)', async () => {
    renderPatientPage();

    const plankCard = screen.getByTestId('exercise-card-plank');
    fireEvent.keyDown(plankCard, { key: 'Enter', code: 'Enter' });

    expect(await screen.findByRole('dialog')).toBeDefined();
    expect(screen.getAllByRole('heading', { name: 'Plank' }).length).toBeGreaterThan(0);
  });

  it('provides an accessibility toolbar with text scaling and high contrast toggle', () => {
    renderPatientPage();

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

  it('links the Record / Upload button to /patient/upload without a made-up plan exercise id', () => {
    renderPatientPage();

    const uploadButtons = screen.getAllByRole('link', { name: /record \/ upload/i });
    expect(uploadButtons.length).toBe(MOCK_ASSIGNED_EXERCISES.length);

    const firstButton = uploadButtons[0];
    expect(firstButton.getAttribute('href')).toBe(
      `/patient/upload?exercise=${MOCK_ASSIGNED_EXERCISES[0].name}`,
    );
  });

  it('says the exercises are sample data', () => {
    renderPatientPage();
    expect(screen.getByText('Sample data')).toBeDefined();
  });

  it('shows processing notification when redirected after a session upload', () => {
    renderPatientPage([
      {
        pathname: '/patient',
        state: { uploadedSessionId: 'sess-987-abc' },
      },
    ]);

    expect(screen.getByText('Upload in Progress')).toBeDefined();
    expect(screen.getByText('sess-987-abc')).toBeDefined();
    expect(screen.getByText('processing')).toBeDefined();
  });
});
