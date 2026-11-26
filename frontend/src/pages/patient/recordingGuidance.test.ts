import { describe, expect, it } from 'vitest';

import {
  GENERAL_RECORDING_TIPS,
  RECORDING_GUIDANCE,
  getRecordingGuidance,
  type ExerciseName,
} from './recordingGuidance';

// The exercise library, by the names in the API (docs/analysis-result.md, Exercise names).
const EXERCISES: ExerciseName[] = [
  'squat',
  'plank',
  'side_leg_raise',
  'shoulder_abduction',
  'cat_cow',
];

describe('RECORDING_GUIDANCE', () => {
  it('has guidance for each of the 5 exercises of the library, and for no other', () => {
    expect(Object.keys(RECORDING_GUIDANCE).sort()).toEqual([...EXERCISES].sort());
  });

  it.each(EXERCISES)('fills in every part of the guidance for %s', (name) => {
    const { tips, ...camera } = RECORDING_GUIDANCE[name];

    for (const text of Object.values(camera)) {
      expect(text.trim()).not.toBe('');
    }
    expect(tips.length).toBeGreaterThan(0);
    for (const tip of tips) {
      expect(tip.trim()).not.toBe('');
    }
  });
});

describe('getRecordingGuidance', () => {
  it("finds an exercise's guidance by its name in the API", () => {
    expect(getRecordingGuidance('plank')).toBe(RECORDING_GUIDANCE.plank);
  });

  it('finds none for an exercise without guidance, or a name that is not an exercise', () => {
    expect(getRecordingGuidance('lunge')).toBeUndefined();
    expect(getRecordingGuidance('toString')).toBeUndefined();
  });
});

describe('GENERAL_RECORDING_TIPS', () => {
  it('gives the clip length that the upload checks allow', () => {
    expect(GENERAL_RECORDING_TIPS).toContain(
      'Each video must be between 3 seconds and 2 minutes long.',
    );
  });
});
