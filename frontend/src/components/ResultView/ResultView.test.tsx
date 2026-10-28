import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ResultView } from './ResultView';
import type { AnalysisResult } from './types';
import squat from '../../../../docs/analysis-result-examples/squat.json';
import squatZero from '../../../../docs/analysis-result-examples/squat-zero-reps.json';
import sideLegRaise from '../../../../docs/analysis-result-examples/side-leg-raise.json';
import plank from '../../../../docs/analysis-result-examples/plank.json';
import plankNoHold from '../../../../docs/analysis-result-examples/plank-no-hold.json';
import failedNoPerson from '../../../../docs/analysis-result-examples/failed-no-person.json';
import failedTimedOut from '../../../../docs/analysis-result-examples/failed-timed-out.json';

// Vitest globals are off, so Testing Library doesn't unmount between tests by itself.
afterEach(cleanup);

function show(result: unknown, onReupload?: () => void) {
  return render(
    <MantineProvider>
      <ResultView result={result as AnalysisResult} onReupload={onReupload} />
    </MantineProvider>,
  );
}

const text = (id: string) => screen.getByTestId(id).textContent;
const band = (id: string) => screen.getByTestId(id).getAttribute('data-band');

describe('ResultView', () => {
  it('shows reps, score, feedback and rep issues (squat)', () => {
    show(squat);
    expect(text('main-value')).toBe('3');
    expect(screen.getByText('reps')).toBeDefined();
    expect(band('form-score')).toBe('good');
    expect(band('rep-2-score')).toBe('fair');
    expect(screen.getByText('Your knees moved inward.')).toBeDefined();
    expect(screen.getByText(/Slow down/)).toBeDefined();
  });

  it('shows 0 reps and no score when zero reps (squat-zero-reps)', () => {
    show(squatZero);
    expect(text('main-value')).toBe('0');
    expect(screen.getByText('reps')).toBeDefined();
    expect(screen.queryByTestId('form-score')).toBeNull();
    expect(screen.getByText(/didn't see a full rep or hold/)).toBeDefined();
  });

  it('labels left and right sides (side-leg-raise)', () => {
    show(sideLegRaise);
    expect(text('main-value')).toBe('4');
    expect(text('rep-1')).toContain('Left');
    expect(text('rep-3')).toContain('Right');
  });

  it('shows hold time, not reps, for a plank', () => {
    show(plank);
    expect(text('main-value')).toBe('22.0');
    expect(screen.getByText('seconds held')).toBeDefined();
    expect(screen.queryByText('reps')).toBeNull();
    expect(text('rep-1')).toContain('Hold 1');
    expect(band('rep-1-score')).toBe('fair');
  });

  it('shows 0.0 seconds held when no hold was seen (plank-no-hold)', () => {
    show(plankNoHold);
    expect(text('main-value')).toBe('0.0');
    expect(screen.getByText('seconds held')).toBeDefined();
    expect(screen.queryByTestId('form-score')).toBeNull();
  });

  it.each([
    ['no_person', failedNoPerson],
    ['analysis_timed_out', failedTimedOut],
  ])('shows the message and a re-upload button for %s', (_code, result) => {
    const onReupload = vi.fn();
    show(result, onReupload);
    expect(screen.getByTestId('result-failed')).toBeDefined();
    expect(screen.getByText(result.error_message as string)).toBeDefined();
    expect(screen.queryByTestId('main-value')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Upload again' }));
    expect(onReupload).toHaveBeenCalledTimes(1);
  });

  it('does not offer a re-upload for unknown_exercise', () => {
    show(
      { ...failedNoPerson, error_code: 'unknown_exercise', error_message: 'Unknown exercise.' },
      vi.fn(),
    );
    expect(screen.queryByRole('button', { name: 'Upload again' })).toBeNull();
  });
});
