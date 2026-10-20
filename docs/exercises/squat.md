# Squat

From standing, the patient bends the knees and hips to lower the body, then stands back up. One trip down and back up is one rep.

| Name in the API | Kind | Sides | Minimum rep time |
| --- | --- | --- | --- |
| `squat` | Reps | None (`side` is null) | 2 seconds |

Every number on this page is a starting value from the prototype, not a clinical target (see [Thresholds are starting values](README.md#thresholds-are-starting-values)). The rules shared by every exercise are in [Rules for every exercise](README.md#rules-for-every-exercise).

## Camera

- Stand sideways to the phone, so it sees the side of your body. Either side can face the phone.
- Put the phone upright (portrait) on a stable surface, such as a shelf or a stand. Do not hold it.
- Set it at about hip height, 2 to 3 meters (7 to 10 feet) away.
- Your whole body, from your head to your feet, must stay in the frame for the whole video, including at the bottom of each squat.
- Film in good light, with only you in the frame.
- Stand with your feet about hip-width apart. Hold your arms out in front of you, so they do not cover your hip.
- Start standing tall, stand all the way up between squats, and end standing tall.

**Start position:** standing tall and side-on to the phone, knees straight, feet about hip-width apart, arms in front.

## Required joints

On the side nearer the camera (see [Measuring](README.md#measuring)):

- `{side}_shoulder`
- `{side}_hip`
- `{side}_knee`
- `{side}_ankle`

No other joint is checked: not the nose, the heels, the toes, or the far side of the body.

## Measurements

| Signal | How | Meaning |
| --- | --- | --- |
| Knee angle | `joint_angle({side}_hip, {side}_knee, {side}_ankle, width, height)` | 180° with a straight leg. Smaller as the knee bends |
| Torso lean | `lean_from_vertical({side}_shoulder, {side}_hip, width, height)` | 0° when the shoulder is straight above the hip, up to 90° |

**Which way the patient faces:** it does not matter. Both measurements are unsigned, so they read the same whether the patient faces left or right in the image. No x flip is needed.

## Counting reps

All steps use the knee angle.

| Step | Knee angle | What happens |
| --- | --- | --- |
| Start position | 165° or more | Standing tall. The analyzer waits for this before the first rep, and again after a dropped rep |
| Rep starts | 155° or less | The patient is going down. This time is `start_seconds` |
| Bottom (count threshold) | 145° or less | The rep will count when the patient stands back up |
| Rep ends | 165° or more, after the bottom | The rep counts. This time is `end_seconds` |

- Back to 165° or more without reaching 145°: a small dip, not a rep, and no issues. The patient is in the start position again.
- The 10° gap between 165° and 155° keeps noise while standing from starting a rep. Once the bottom is reached it stays reached for that rep, so a wobble at the bottom cannot count twice.
- A patient who does not stand all the way up (165°) between squats gets one long rep, not two.
- There is no longest rep time. A slow rep still counts.
- Tracking lost during a rep: see [Measuring](README.md#measuring).

## Form rules

Checked over the whole rep (see [Reps](README.md#reps)).

| Code | Rule | Message | Tip | Penalty |
| --- | --- | --- | --- | --- |
| `leaning_forward` | Largest torso lean in the rep is above 45° | Your chest leaned far forward. | Keep your chest up as you squat. | 30 |
| `not_deep_enough` | Smallest knee angle in the rep is above 110° | Your squat was not very deep. | Sit your hips lower, as far as feels comfortable. | 10 |
| `too_fast` | The rep took less than 2 seconds (see [Too fast](README.md#too-fast-every-exercise-done-in-reps)) | This rep took less than 2 seconds. | Slow down: take at least 2 seconds for each rep. | 10 |

A rep that only just reaches the count threshold (145°) is counted and gets `not_deep_enough`. A squat to 110° or lower passes the depth rule.

## Metrics

| Name | Meaning |
| --- | --- |
| `min_knee_angle_degrees` | Smallest knee angle during the rep. Lower means deeper |
| `max_torso_lean_degrees` | Largest torso lean during the rep. 0 is upright |

## Limits

- **Knees moving inward** cannot be seen from the side, so they are not checked. The placeholder code `knees_cave_in` in `docs/analysis-result-examples/squat.json` is not a squat issue.
- **Heels lifting** off the floor is not checked.
- **The camera must be truly side-on.** All angles are 2D. If the patient turns toward or away from the phone, the knee angle reads larger and the lean smaller, so the squat looks shallower and more upright than it is. For example, a squat that measures 110° from the side reads about 126° when the patient is turned 45°, and gets `not_deep_enough`.
- **Only the near leg is measured.** The far leg is not checked, so uneven weight, or a lunge, is not seen.
- **The torso is a straight line** from shoulder to hip, so a rounded back is not seen. The lean is unsigned, so leaning back also counts as lean (not expected in a squat).
