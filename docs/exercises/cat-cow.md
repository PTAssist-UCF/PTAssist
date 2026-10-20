# Cat-cow

On hands and knees, the patient rounds the back up toward the ceiling and tucks the chin (cat), then lets the belly sink and lifts the chest and head (cow). One cat and one cow is one rep.

| Name in the API | Kind | Sides | Minimum rep time |
| --- | --- | --- | --- |
| `cat_cow` | Reps | None (`side` is null) | 3 seconds |

The prototype has no cat-cow, so every number on this page is a new starting value, not a clinical target (see [Thresholds are starting values](README.md#thresholds-are-starting-values)). The minimum rep time is 3 seconds because this is a slow stretch. The rules shared by every exercise are in [Rules for every exercise](README.md#rules-for-every-exercise).

## Camera

- Get on your hands and knees side-on to the phone, so it sees the side of your body. Your head can point either way.
- Put the phone on its side (landscape) on the floor or a low step, propped so it cannot move. Do not hold it.
- If you can, set it about as high as your hips are when you are on your hands and knees. Place it 2 to 3 meters (7 to 10 feet) away.
- Your whole body, from your head to your knees and feet, must stay in the frame for the whole video.
- Film in good light, with only you in the frame.
- Put your hands under your shoulders and your knees under your hips. Keep your arms straight.
- Start in the start position and hold still for about 1 second before your first rep.
- Cat: round your back up toward the ceiling and tuck your chin. Cow: let your belly sink, lift your chest and head, and look forward. Move slowly.
- You can pause in the start position between reps, or flow from one rep into the next. Stay on your hands and knees, and end in the start position.

**Start position:** on your hands and knees, side-on to the phone, hands under your shoulders, knees under your hips, arms straight, back flat, and head in line with your back.

## Required joints

On the side nearer the camera (see [Measuring](README.md#measuring)):

- `{side}_ear`
- `{side}_shoulder`
- `{side}_elbow`
- `{side}_wrist`
- `{side}_hip`
- `{side}_knee`

No other joint is checked: not the nose, the ankles, the feet, or the far side of the body.

## Measurements

MediaPipe has no points on the spine, so rounding and arching the back are measured through the head, which follows the back in this exercise (chin tucked in the cat, head up in the cow).

| Signal | How | Meaning |
| --- | --- | --- |
| Head angle | `-signed_segment_angle({side}_hip, {side}_shoulder, {side}_shoulder, {side}_ear, width, height)`, after the x flip | The neck (shoulder to ear) against the trunk (hip to shoulder). Rises as the head lifts (cow), falls as the chin tucks (cat) |
| Head change | Head angle minus neutral (see [Counting reps](#counting-reps)) | 0 in the start position. Positive toward the cow, negative toward the cat |
| Elbow angle | `joint_angle({side}_shoulder, {side}_elbow, {side}_wrist, width, height)` | 180° with a straight arm. Smaller as the elbow bends |
| Thigh angle | `lean_from_vertical({side}_hip, {side}_knee, width, height)` | 0° when the knee is straight below the hip, up to 90° |
| Trunk tilt | `90 - lean_from_vertical({side}_shoulder, {side}_hip, width, height)` | 0° when the shoulder and hip are level, 90° when upright |

**On hands and knees:** the trunk tilt and the thigh angle are both 45° or less. This rules out standing, kneeling upright, sitting back on the heels, and lying down. A frame that is not on hands and knees is skipped, like a frame that is not tracked.

**Which way the patient faces:** the patient faces right when the shoulder is to the right of the hip in the image (larger x). Otherwise, flip x before measuring (see [Measuring](README.md#measuring)). Decide this on each frame. Only the head angle needs the flip; the other signals are unsigned. Checked with the helpers in a 1280 x 720 landscape frame: image y grows downward, so `signed_segment_angle(hip, shoulder, shoulder, ear)` is negative when the ear rises, hence the minus sign. After the flip, lifting the head gives a positive head angle whichever way the patient faces. Without the flip, the sign is reversed for a patient facing left.

## Counting reps

**Neutral** is the median head angle over the first second on hands and knees: the used frames from the first used frame to 1 second after it. It is set once per video. Head angles differ from person to person, so all steps use the head change from neutral.

| Step | Head change | What happens |
| --- | --- | --- |
| Start position | Between -5° and 5° | The analyzer waits for this once neutral is set, and again after a dropped rep |
| Rep starts | Below -5° or above 5° | The head left neutral. This time is `start_seconds` |
| Cat | -15° or less | Once reached, it stays reached for this rep |
| Cow | 15° or more | Once reached, it stays reached for this rep |
| Rep ends | Back between -5° and 5°, after both the cat and the cow | The rep counts. This time is `end_seconds` |

- Back between -5° and 5° before reaching the cat or the cow: a small movement, not a rep, and no issues.
- The count threshold is reaching both the cat and the cow, in either order. Passing through neutral after only one of them does not end the rep, so the patient can pause in the start position between the cat and the cow.
- In a flowing set, one rep ends as the head comes down from the cow through neutral, and the next starts as it goes on toward the cat.
- The rep start and end use the same 5° line, with no gap. None is needed: a rep counts only after both the cat and the cow, 30° apart, so noise near 5° can only start movements that never count.
- A rep that has not reached both the cat and the cow by the end of the video is not a rep, and gets no issues.
- Sitting back, standing up, or lying down during a rep for more than 0.75 seconds drops it, like lost tracking (see [Measuring](README.md#measuring)).
- There is no longest rep time. A slow rep still counts.

## Form rules

Checked over the whole rep (see [Reps](README.md#reps)).

| Code | Rule | Message | Tip | Penalty |
| --- | --- | --- | --- | --- |
| `small_movement` | Head swing (highest minus lowest head angle in the rep) is below 45° | You did not move very far into the cat and the cow. | Round your back higher and tuck your chin, then let your belly sink and lift your head. | 10 |
| `arms_bent` | Smallest elbow angle in the rep is below 150° | Your arms bent at the elbows. | Keep your arms straight, with your hands under your shoulders. | 10 |
| `hips_rock` | Largest thigh angle in the rep is above 20° | Your hips rocked forward or back. | Keep your hips over your knees and move only your back. | 10 |
| `too_fast` | The rep took less than 3 seconds (see [Too fast](README.md#too-fast-every-exercise-done-in-reps)) | This rep took less than 3 seconds. | Slow down: take at least 3 seconds for each rep. | 10 |

- Every counted rep swings at least 30° (from -15° to 15°), so a rep that only just counts gets `small_movement`. A swing of 45° or more, for example 25° each way, passes.
- The thigh check for being on hands and knees (45°) is wider than the `hips_rock` threshold (20°), so a rep with rocking is still measured and gets the issue.

## Metrics

| Name | Meaning |
| --- | --- |
| `head_swing_degrees` | Highest minus lowest head angle during the rep. Larger means a bigger cat and cow |

## Limits

- **The spine is not tracked.** This is the main risk. A patient who moves only the head, with a still back, is counted with good form. One who moves the back but keeps the head still gets `small_movement`, or no reps. The labeled test set (SCRUM-54) will show whether the head is a good enough stand-in.
- **Neutral is set once.** If the patient is still moving in the first second, or their resting head position drifts later, every step shifts. A last rep whose head does not come back within 5° of neutral is not counted.
- **The camera must be truly side-on.** All angles are 2D. If the patient turns toward or away from the phone, forward and back movement looks shorter: the head swing reads larger and rocking reads smaller. For example, a 20° rock reads about 14° when the patient is turned 45°, so `hips_rock` is missed.
- **Elbows that bend out to the side** (toward or away from the phone) look straight, so `arms_bent` can miss them.
- **Only the near side is measured.** The far arm and leg are not checked.
