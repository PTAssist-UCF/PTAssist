# Shoulder abduction

Facing the camera, the patient lifts one arm, or both, out to the side with the elbow straight, up to at least shoulder height, then lowers it back to the side. One lift and return is one rep.

| Name in the API | Kind | Sides | Minimum rep time |
| --- | --- | --- | --- |
| `shoulder_abduction` | Reps | `"left"`, `"right"`, or `"both"`: the arm that lifts, or both arms together | 2 seconds |

Every number on this page is a starting value, not a clinical target (see [Thresholds are starting values](README.md#thresholds-are-starting-values)). The start and end angles (rounded from the prototype's 22°, 34°, and 25°), the elbow rule, and the lean rule come from the prototype. The 60° count threshold (the prototype used 55°), the 80° height rule, and the 1-second rule for both arms are new. The rules shared by every exercise are in [Rules for every exercise](README.md#rules-for-every-exercise).

## Camera

- Face the phone. You can stand, or sit on a chair without arms.
- Put the phone upright (portrait) on a stable surface, such as a shelf or a stand. Do not hold it.
- Set it at about chest height, about 3 meters (10 feet) away, so your hands stay in the frame when your arms are out to the side.
- From the top of your head to your hips must stay in the frame for the whole video. Leave room above your head and at both sides for your hands when your arms are raised.
- Film in good light, with only you in the frame.
- Lift one arm, or both, out to the side with your elbow straight, up to at least shoulder height, then lower it slowly back to your side. Keep an arm you are not using relaxed at your side.
- Start with both arms at your sides, bring your arm all the way down between lifts, and end with both arms at your sides.

**Start position:** facing the phone, standing or sitting tall, both arms relaxed at your sides.

## Required joints

- Always: `left_shoulder`, `right_shoulder`, `left_hip`, `right_hip`. A frame without all four is skipped for both arms.
- For each arm: `{side}_elbow` and `{side}_wrist`, where `{side}` is `left` or `right`. An arm is measured only on frames where its elbow and wrist also pass `is_frame_visible`. The other arm is measured on its own.

No other joint is checked: not the head, the fingers, or the legs. This is a front view, so there is no near side to pick.

## Measurements

`shoulder_mid` is `midpoint(left_shoulder, right_shoulder)` and `hip_mid` is `midpoint(left_hip, right_hip)`.

| Signal | How | Meaning |
| --- | --- | --- |
| Shoulder angle (each arm) | `abs(signed_segment_angle(shoulder_mid, hip_mid, {side}_shoulder, {side}_elbow, width, height))` | 0° with the arm along the body, 90° at shoulder height, 180° straight overhead. Measured from the torso line, not from the image's vertical |
| Elbow angle (each arm) | `joint_angle({side}_shoulder, {side}_elbow, {side}_wrist, width, height)` | 180° with a straight elbow. Smaller as it bends |
| Torso lean | `lean_from_vertical(shoulder_mid, hip_mid, width, height)` | 0° when the shoulders are straight above the hips, up to 90°, to either side |

**Which way the patient faces:** toward the phone. No x flip is needed, because every signal is unsigned. The `abs()` matters: without it, the shoulder angle is negative for one arm and positive for the other, and an arm straight overhead can read -180° or 180°. Checked with the helpers in a 720 x 1280 portrait frame: each arm reads 0°, 90°, and 180° at its side, at shoulder height, and overhead.

## Counting reps

Each arm is counted on its own, with its own shoulder angle.

| Step | Shoulder angle | What happens |
| --- | --- | --- |
| Start position | 25° or less | Arm at the side. The analyzer waits for this before that arm's first rep, and again after a dropped rep |
| Rep starts | 35° or more | The arm is lifting. This time is `start_seconds` |
| Count threshold | 60° or more | The rep will count when the arm comes back down |
| Rep ends | 25° or less, after the count threshold | The rep counts, with that arm as its `side`. This time is `end_seconds` |

- Back to 25° or less without reaching 60°: a small lift, not a rep, and no issues.
- The 10° gap between 25° and 35° keeps noise from starting a rep. Once 60° is reached it stays reached for that rep, so a wobble at the top cannot count twice.
- There is no longest rep time. A slow rep still counts.
- If the arm's tracking (the four torso joints, its elbow, or its wrist) is lost for more than 0.75 seconds during its rep, that rep is dropped (see [Measuring](README.md#measuring)).

### Both arms

When both arms lift together, the two one-arm reps become one rep with `side: "both"`:

- Go through the counted reps in the order they started. Pair each unpaired rep with the next unpaired rep of the other arm, if that one starts within 1 second after it. Each rep is paired at most once.
- The paired rep starts at the earlier start and ends at the later end.
- Its issues are every issue either arm's rep had, each code once, except `too_fast`, which is checked on the paired rep's own start and end.
- Its `max_shoulder_angle_degrees` is the lower of the two arms' values.
- A rep with no partner keeps its own side. If one arm's rep was dropped or did not reach 60°, the other arm's rep is a one-arm rep.

## Form rules

Checked over each arm's whole rep (see [Reps](README.md#reps)), then combined for `both` reps as above.

| Code | Rule | Message | Tip | Penalty |
| --- | --- | --- | --- | --- |
| `torso_lean` | Largest torso lean in the rep is above 18° | You leaned your upper body to the side. | Keep your body upright and lift only your arm. | 30 |
| `arm_not_high_enough` | Largest shoulder angle in the rep is below 80° | Your arm did not reach shoulder height. | Lift your arm higher, to shoulder height or above if you can. | 10 |
| `elbow_bent` | Smallest elbow angle in the rep, on frames where the shoulder angle is 55° or more, is below 150° | Your elbow bent as you lifted your arm. | Keep your elbow straight as you lift and lower your arm. | 10 |
| `too_fast` | The rep took less than 2 seconds (see [Too fast](README.md#too-fast-every-exercise-done-in-reps)) | This rep took less than 2 seconds. | Slow down: take at least 2 seconds for each rep. | 10 |

- A rep that only just reaches the count threshold (60°) is counted and gets `arm_not_high_enough`. A lift to 80° or higher passes.
- Every counted rep reaches 60°, so it always has frames for the elbow rule.

## Metrics

| Name | Meaning |
| --- | --- |
| `max_shoulder_angle_degrees` | Largest shoulder angle during the rep: 90 is shoulder height, 180 is overhead. For a `both` rep, the lower of the two arms |

## Limits

- **Sideways, forward, and across-the-body lifts can look alike.** All angles are 2D. A lift forward toward the phone, or across the front of the body, can read like a lift to the side and count as a rep.
- **Shrugging and shoulder-blade movement** are not checked.
- **A tilted phone shows up as torso lean.** A phone tilted 10° to one side adds about 10° to the torso lean of an upright patient. The shoulder and elbow angles do not change, because they compare body parts with each other, not with the image.
- **Leaning toward or away from the phone** is not seen. Only leaning to the side is.
- **An elbow that bends toward or away from the phone** can look straight, so `elbow_bent` can miss it.
- **Facing the phone is not checked.** If the patient turns sideways, the angles are wrong.
- **A mirrored video swaps the arms.** If a phone saves a front-camera video mirrored, MediaPipe labels the left arm as the right one, so `side` is swapped.
