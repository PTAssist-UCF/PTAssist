/**
 * How the patient pages describe the exercises of a plan (GET /plans/me), and the link
 * to upload a video for one of them.
 */
import type { PlanExerciseResponse } from '@/api/model';

/** "1 set", "3 sets". */
function count(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

/**
 * The target for each time the patient does the exercise: "3 sets × 10 reps", or
 * "3 sets × 30-second hold" for an exercise held for time (the plank). One video is one
 * set.
 */
export function describeTarget(item: PlanExerciseResponse): string {
  const sets = count(item.sets, 'set');
  // The API sets exactly one of the two: reps for an exercise done in reps, hold_seconds
  // for one held for time.
  if (item.reps !== null) {
    const reps = count(item.reps, 'rep');
    // The side-lying leg raise's target counts the reps of both legs together, like its
    // result's rep_count (backend/README.md, Data model): 20 reps is 10 per leg. Without
    // this, "20 reps" reads as 20 per leg.
    return item.exercise.name === 'side_leg_raise'
      ? `${sets} × ${reps} total across both sides`
      : `${sets} × ${reps}`;
  }
  return `${sets} × ${item.hold_seconds}-second hold`;
}

/** How many days a week to do the exercise: "Once a week", "3 times a week". */
export function describeFrequency(timesPerWeek: number): string {
  return timesPerWeek === 1 ? 'Once a week' : `${timesPerWeek} times a week`;
}

/**
 * The upload page for one exercise of the plan. The plan exercise's id is the
 * plan_exercise_id that POST /sessions takes with the video.
 */
export function uploadPath(planExerciseId: string): string {
  return `/patient/upload?plan_exercise_id=${encodeURIComponent(planExerciseId)}`;
}
