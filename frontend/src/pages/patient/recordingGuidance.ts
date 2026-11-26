/**
 * How to film each exercise, for the recording tips on the upload page (SCRUM-97): where
 * the phone goes, what must stay in the frame, the start position, and how to move and
 * finish. Taken from the Camera section of each exercise's spec in docs/exercises/, which is
 * written to be shown to a patient. When a spec's Camera section changes, change its entry
 * here too.
 */
import { MAX_VIDEO_SECONDS, MIN_VIDEO_SECONDS } from '@/utils/videoValidation';

/**
 * The exercises of the library, by their names in the API (docs/analysis-result.md,
 * Exercise names). RECORDING_GUIDANCE must have an entry for each one, so a name added here
 * without guidance does not compile.
 */
export type ExerciseName = 'squat' | 'plank' | 'side_leg_raise' | 'shoulder_abduction' | 'cat_cow';

/** How to film one exercise, a sentence or two for each part. */
export interface RecordingGuidance {
  /** Which way to face the phone, so it sees the part of the body the analysis measures. */
  view: string;
  /** How to set the phone up: upright (portrait) or on its side (landscape), and on what. */
  phone: string;
  /** How high the phone goes. */
  height: string;
  /** How far away the phone goes. */
  distance: string;
  /** What must stay in the frame for the whole video. */
  framing: string;
  /** The position each video starts in. */
  startPosition: string;
  /** How to get into position, move, and finish, so that every rep (or hold) counts. */
  tips: string[];
}

export const RECORDING_GUIDANCE: Record<ExerciseName, RecordingGuidance> = {
  // docs/exercises/squat.md
  squat: {
    view: 'Stand sideways to the phone, so it sees the side of your body. Either side can face the phone.',
    phone: 'Upright (portrait), on a stable surface such as a shelf or a stand. Do not hold it.',
    height: 'About hip height.',
    distance: '2 to 3 meters (7 to 10 feet) away.',
    framing:
      'Your whole body, from your head to your feet, for the whole video, including at the bottom of each squat.',
    startPosition:
      'Standing tall and side-on to the phone, knees straight, feet about hip-width apart, arms in front.',
    tips: [
      'Stand with your feet about hip-width apart. Hold your arms out in front of you, so they do not cover your hip.',
      'Start standing tall, stand all the way up between squats, and end standing tall.',
    ],
  },
  // docs/exercises/plank.md
  plank: {
    view: 'Get into the plank side-on to the phone, so it sees the side of your body. Your head can point either way.',
    phone: 'On its side (landscape), propped so it cannot move. Do not hold it.',
    height: 'On the floor or a low step, about as high as your hips will be in the plank.',
    distance: '2 to 3 meters (7 to 10 feet) away.',
    framing: 'Your whole body, from your head to your feet, for the whole video.',
    startPosition:
      'On your hands and knees (or forearms and knees), side-on to the phone, with your hips above your knees.',
    tips: [
      'A forearm plank or a straight-arm plank is fine. Put your forearms or hands on the floor, with your elbows or hands under your shoulders. Keep your legs straight and stay up on your toes.',
      'Start in the start position, lift your knees into the plank, and hold. When you finish, lower your knees to the floor and go back to the start position before you stop the video.',
      'To rest during the video, go back to the start position. Do not lie down.',
    ],
  },
  // docs/exercises/side-leg-raise.md
  side_leg_raise: {
    view: 'Lie on your side on a mat, facing the phone, so it sees the front of your body. Your head can point either way.',
    phone: 'On its side (landscape), propped up so it cannot move. Do not hold it.',
    height: 'On the floor.',
    distance:
      'About 3 meters (10 feet) away, in front of the middle of your body, not toward your head or your feet.',
    framing:
      'Your whole body, from your head to your feet, for the whole video, including your top foot at the top of each lift.',
    startPosition:
      'Lying on your side, facing the phone, body in a straight line, legs straight and stacked, head resting on your bottom arm, top hand on the floor in front of your chest.',
    tips: [
      'Rest your head on your bottom arm, and put your top hand on the floor in front of your chest. Keep your body in a straight line, and both legs straight, one on top of the other.',
      'Start in the start position, lower your leg all the way onto your bottom leg between lifts, and end in the start position.',
      'To work your other leg in the same video, lie on your other side in the same spot, still facing the phone. Your head is now at the other end of the mat. Start again from the start position.',
    ],
  },
  // docs/exercises/shoulder-abduction.md
  shoulder_abduction: {
    view: 'Face the phone. You can stand, or sit on a chair without arms.',
    phone: 'Upright (portrait), on a stable surface such as a shelf or a stand. Do not hold it.',
    height: 'About chest height.',
    distance: 'About 3 meters (10 feet) away.',
    framing:
      'From the top of your head to your hips, for the whole video. Leave room above your head and at both sides for your hands when your arms are raised.',
    startPosition: 'Facing the phone, standing or sitting tall, both arms relaxed at your sides.',
    tips: [
      'Lift one arm, or both, out to the side with your elbow straight, up to at least shoulder height, then lower it slowly back to your side. Keep an arm you are not using relaxed at your side.',
      'Start with both arms at your sides, bring your arm all the way down between lifts, and end with both arms at your sides.',
    ],
  },
  // docs/exercises/cat-cow.md
  cat_cow: {
    view: 'Get on your hands and knees side-on to the phone, so it sees the side of your body. Your head can point either way.',
    phone: 'On its side (landscape), propped so it cannot move. Do not hold it.',
    height:
      'On the floor or a low step. If you can, about as high as your hips are when you are on your hands and knees.',
    distance: '2 to 3 meters (7 to 10 feet) away.',
    framing: 'Your whole body, from your head to your knees and feet, for the whole video.',
    startPosition:
      'On your hands and knees, side-on to the phone, hands under your shoulders, knees under your hips, arms straight, back flat, and head in line with your back.',
    tips: [
      'Put your hands under your shoulders and your knees under your hips. Keep your arms straight.',
      'Start in the start position and hold still for about 1 second before your first rep.',
      'Cat: round your back up toward the ceiling and tuck your chin. Cow: let your belly sink, lift your chest and head, and look forward. Move slowly.',
      'You can pause in the start position between reps, or flow from one rep into the next. Stay on your hands and knees, and end in the start position.',
    ],
  },
};

/**
 * Shown for every exercise, after its own tips: the tip that every spec's Camera section
 * shares, and the clip length that the upload checks allow (src/utils/videoValidation.ts).
 */
export const GENERAL_RECORDING_TIPS = [
  'Film in good light, with only you in the frame.',
  `Each video must be between ${MIN_VIDEO_SECONDS} seconds and ${MAX_VIDEO_SECONDS / 60} minutes long.`,
];

/**
 * The guidance for an exercise, by its name in the API (the plan exercise's exercise.name).
 * None for an exercise without an entry, such as one added to the library later.
 */
export function getRecordingGuidance(name: string): RecordingGuidance | undefined {
  // Own properties only, so a name such as "toString" finds nothing.
  return Object.hasOwn(RECORDING_GUIDANCE, name)
    ? RECORDING_GUIDANCE[name as ExerciseName]
    : undefined;
}
