export type ScoreBand = 'good' | 'fair' | 'needs-work';

export function getScoreBand(score: number): ScoreBand {
  if (score >= 80) return 'good';
  if (score >= 50) return 'fair';
  return 'needs-work';
}

export const BAND_COLOR: Record<ScoreBand, string> = {
  good: 'green',
  fair: 'yellow',
  'needs-work': 'red',
};

export const BAND_LABEL: Record<ScoreBand, string> = {
  good: 'Good',
  fair: 'Fair',
  'needs-work': 'Needs work',
};
