# Side-lying leg raise

The patient lies on one side with both legs straight and stacked, lifts the top leg toward the ceiling, and lowers it back onto the bottom leg. One lift and lower is one rep. The leg that lifts is the rep's side.

| Name in the API | Kind | Sides | Minimum rep time |
| --- | --- | --- | --- |
| `side_leg_raise` | Reps | `"left"` or `"right"`: the leg that lifts | 2 seconds |

The prototype has no side-lying leg raise, so every number on this page is a new starting value, not a clinical target (see [Thresholds are starting values](README.md#thresholds-are-starting-values)). The rules shared by every exercise are in [Rules for every exercise](README.md#rules-for-every-exercise).

## Camera

- Lie on your side on a mat, facing the phone, so it sees the front of your body. Your head can point either way.
- Put the phone on its side (landscape) on the floor, propped up so it cannot move. Do not hold it.
- Put it in front of the middle of your body, not toward your head or your feet, about 3 meters (10 feet) away, so your top foot stays in the frame at the top of each lift.
- Your whole body, from your head to your feet, must stay in the frame for the whole video, including your top foot at the top of each lift.
- Film in good light, with only you in the frame.
- Rest your head on your bottom arm, and put your top hand on the floor in front of your chest. Keep your body in a straight line, and both legs straight, one on top of the other.
- Start in the start position, lower your leg all the way onto your bottom leg between lifts, and end in the start position.
- To work your other leg in the same video, lie on your other side in the same spot, still facing the phone. Your head is now at the other end of the mat. Start again from the start position.

**Start position:** lying on your side, facing the phone, body in a straight line, legs straight and stacked, head resting on your bottom arm, top hand on the floor in front of your chest.

## Required joints

- `left_hip`, `right_hip`
- `left_ankle`, `right_ankle`
- `{top}_shoulder`: the shoulder on the side of the top leg (see [Measurements](#measurements))

Both legs are required, because the top leg is measured against the bottom leg. No other joint is checked: not the nose, the knees, the bottom shoulder, the arms, the heels, or the toes.

## Measurements

**Which leg is on top:** the leg whose hip is higher in the image (smaller y). Below, `top_hip` means that leg's hip (for example `left_hip`), and `bottom_hip` the other leg's. The rep's `side` is the top leg's name: `"left"` for `left_...`, `"right"` for `right_...`. Decide it on each frame while no rep is in progress, and keep it fixed from `start_seconds` to `end_seconds`. Use the hip heights, not the names, to find it (see [Limits](#limits)). When the top leg changes (the patient turned over), reset the smoothers.

**Which way the patient lies:** the feet point right when `bottom_ankle` is to the right of `bottom_hip` in the image (larger x). Otherwise, flip x before measuring (see [Measuring](README.md#measuring)). Decide this on each frame. All signals below are measured after the flip.

| Signal | How | Meaning |
| --- | --- | --- |
| Leg raise angle | `signed_segment_angle(top_hip, top_ankle, bottom_hip, bottom_ankle, width, height)` | How far the top leg is lifted above the bottom leg. Larger as the leg lifts. With the legs stacked it reads a few degrees below 0° (about −5° to −15°), because the hips are farther apart than the ankles |
| Trunk angle | `signed_segment_angle(bottom_hip, bottom_ankle, top_shoulder, top_hip, width, height)` | Angle of the upper body against the bottom leg. Only how much it changes during a rep is used |

- Both angles use the bottom leg, which lies still on the floor, as the reference line, so a tilted phone does not change them.
- Keep the joint order. In the trunk angle, both segments point toward the feet, so it stays near 0° and never jumps between +180° and −180°.
- Checked with the helpers on synthetic landmarks: after the flip, stacked legs read about −9° and a 30° lift reads about 21°, whichever way the patient lies. Without the flip, the sign is reversed when the feet point left: stacked legs read about +9° and a 30° lift about −21°. `lean_from_vertical` is not used for the trunk: a lying trunk is near 90°, where it folds, so a 20° movement can read as 3°.

## Counting reps

All steps use the leg raise angle.

| Step | Leg raise angle | What happens |
| --- | --- | --- |
| Start position | 5° or less | Legs together. The analyzer waits for this before the first rep, and again after a dropped rep |
| Rep starts | 10° or more | The top leg is lifting. This time is `start_seconds`. The top leg is now fixed for this rep |
| Top (count threshold) | 15° or more | The rep will count when the leg comes back down |
| Rep ends | 5° or less, after the top | The rep counts. This time is `end_seconds` |

- Back to 5° or less without reaching 15°: a small lift, not a rep, and no issues.
- The 5° gap between 5° and 10° keeps noise from starting a rep. Once the top is reached it stays reached for that rep, so a wobble at the top cannot count twice.
- If the other hip becomes the higher one during a rep, the patient is turning over (or the labels swapped). The rep is dropped.
- Both sides may be in one video. `rep_count` is the total for both sides (see [Sides](../analysis-result.md#sides)).
- There is no longest rep time. A slow rep still counts.
- Tracking lost during a rep: see [Measuring](README.md#measuring).

## Form rules

Checked over the whole rep (see [Reps](README.md#reps)).

| Code | Rule | Message | Tip | Penalty |
| --- | --- | --- | --- | --- |
| `leg_not_high_enough` | Largest leg raise angle in the rep is below 30° | Your leg lift was not very high. | Lift your top leg higher, as far as feels comfortable. | 10 |
| `torso_moves` | At some point in the rep, the trunk angle is more than 10° away from its value at `start_seconds` | Your upper body moved as you lifted your leg. | Keep your upper body still and lift only your leg. | 10 |
| `too_fast` | The rep took less than 2 seconds (see [Too fast](README.md#too-fast-every-exercise-done-in-reps)) | This rep took less than 2 seconds. | Slow down: take at least 2 seconds for each rep. | 10 |

A rep that only just reaches the count threshold (15°) is counted and gets `leg_not_high_enough`. A lift to 30° or more passes. The placeholder code `torso_lean` in `docs/analysis-result-examples/side-leg-raise.json` is `torso_moves` here.

## Metrics

| Name | Meaning |
| --- | --- |
| `max_leg_raise_degrees` | Largest leg raise angle during the rep. Higher means a bigger lift. Stacked legs read a few degrees below 0 |

## Limits

- **The leg drifting forward** (toward the phone) and **the hips rolling back** happen toward or away from the camera, so they are not seen.
- **A bent knee is not checked.** Bending the top knee moves the foot back, away from the camera, so in the image the leg still looks straight (checked with the helpers: a 45° bend reads 180° at the knee). A rule for it would almost never fire.
- **Left and right labels can swap** when the body is lying down. The top leg is found from the hip heights, so the measurements still use the leg that lifts. But a swap gives the wrong `side`, and a swap during a rep drops it.
- **The lift is measured against the bottom leg**, so it reads less than how far the leg moved from rest: about 9° less in the synthetic check, more for wider hips. Moving the bottom leg also changes it.
- **The phone must face the front of the body.** All angles are 2D. Seen at a slant, from toward the head or the feet, the lift reads higher than it is.
- **The trunk is a straight line** from the top shoulder to the top hip, so a twist or a rounded back is not seen.
