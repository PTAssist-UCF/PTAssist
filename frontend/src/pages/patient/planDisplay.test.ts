import { describe, expect, it } from 'vitest';

import { describeFrequency, describeTarget, uploadPath } from './planDisplay';
import { PLANK, SQUAT } from './testPlan';

describe('describeTarget', () => {
  it('gives sets and reps for an exercise done in reps', () => {
    expect(describeTarget(SQUAT)).toBe('3 sets × 10 reps');
    expect(describeTarget({ ...SQUAT, sets: 1, reps: 1 })).toBe('1 set × 1 rep');
  });

  it('gives sets and a hold time for an exercise held for time', () => {
    expect(describeTarget(PLANK)).toBe('3 sets × 30-second hold');
    expect(describeTarget({ ...PLANK, sets: 1, hold_seconds: 45 })).toBe('1 set × 45-second hold');
  });
});

describe('describeFrequency', () => {
  it('says how many days a week', () => {
    expect(describeFrequency(1)).toBe('Once a week');
    expect(describeFrequency(3)).toBe('3 times a week');
    expect(describeFrequency(7)).toBe('7 times a week');
  });
});

describe('uploadPath', () => {
  it("opens the upload page with the plan exercise's id", () => {
    expect(uploadPath(SQUAT.id)).toBe(`/patient/upload?plan_exercise_id=${SQUAT.id}`);
  });
});
