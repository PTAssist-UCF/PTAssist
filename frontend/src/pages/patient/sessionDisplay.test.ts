import { describe, expect, it } from 'vitest';

import { describeCount, resultPath } from './sessionDisplay';

describe('describeCount', () => {
  it('gives the reps of an exercise done in reps', () => {
    expect(describeCount({ rep_count: 3, hold_seconds: null })).toBe('3 reps');
    expect(describeCount({ rep_count: 1, hold_seconds: null })).toBe('1 rep');
    expect(describeCount({ rep_count: 0, hold_seconds: null })).toBe('0 reps');
  });

  it('gives the hold time of an exercise held for time, even a hold of 0 seconds', () => {
    expect(describeCount({ rep_count: null, hold_seconds: 22 })).toBe('22.0 seconds held');
    expect(describeCount({ rep_count: null, hold_seconds: 0 })).toBe('0.0 seconds held');
  });
});

describe('resultPath', () => {
  it("gives the address of a session's result page", () => {
    expect(resultPath('a1b2c3d4-0001-4e5f-8a9b-0c1d2e3f4a5b')).toBe(
      '/patient/history/a1b2c3d4-0001-4e5f-8a9b-0c1d2e3f4a5b',
    );
    expect(resultPath('a/b')).toBe('/patient/history/a%2Fb');
  });
});
