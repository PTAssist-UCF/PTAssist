# Plank

The patient holds the body in a straight line from shoulders to ankles, resting on the forearms (forearm plank) or the hands (straight-arm plank) and the toes. It is held for time, not done in reps. Each unbroken hold is one entry in `reps`.

| Name in the API | Kind | Sides | Minimum rep time |
| --- | --- | --- | --- |
| `plank` | Hold | None (`side` is null) | None (no reps). Holds shorter than 2 seconds are not counted |

The prototype has no plank, so every number on this page is a new starting value, not a clinical target (see [Thresholds are starting values](README.md#thresholds-are-starting-values)). The rules shared by every exercise are in [Rules for every exercise](README.md#rules-for-every-exercise).

## Camera

- Get into the plank side-on to the phone, so it sees the side of your body. Your head can point either way.
- Put the phone on its side (landscape) on the floor or a low step, propped so it cannot move. Do not hold it.
- The phone should be about as high as your hips will be in the plank, 2 to 3 meters (7 to 10 feet) away.
- Your whole body, from your head to your feet, must stay in the frame for the whole video.
- Film in good light, with only you in the frame.
- A forearm plank or a straight-arm plank is fine. Put your forearms or hands on the floor, with your elbows or hands under your shoulders. Keep your legs straight and stay up on your toes.
- Start in the start position, lift your knees into the plank, and hold. When you finish, lower your knees to the floor and go back to the start position before you stop the video. To rest during the video, go back to the start position. Do not lie down.

**Start position:** on your hands and knees (or forearms and knees), side-on to the phone, with your hips above your knees.

## Required joints

On the side nearer the camera (see [Measuring](README.md#measuring)):

- `{side}_shoulder`
- `{side}_elbow`
- `{side}_hip`
- `{side}_knee`
- `{side}_ankle`

No other joint is checked: not the nose, the wrists, the heels, the toes, or the far side of the body.

## Measurements

| Signal | How | Meaning |
| --- | --- | --- |
| Body angle | `90 - lean_from_vertical({side}_shoulder, {side}_ankle, width, height)` | 0° when the shoulder and ankle are level, 90° when standing |
| Knee angle | `joint_angle({side}_hip, {side}_knee, {side}_ankle, width, height)` | 180° with a straight leg. Smaller as the knee bends |
| Upper-arm angle | `lean_from_vertical({side}_shoulder, {side}_elbow, width, height)` | 0° when the elbow is straight below the shoulder, up to 90° |
| Hip angle | `joint_angle({side}_shoulder, {side}_hip, {side}_ankle, width, height)` | 180° when shoulder, hip, and ankle are in a straight line. Smaller when the hips sag or rise |
| Hip side | Sign of `signed_distance_to_line({side}_hip, {side}_ankle, {side}_shoulder, width, height)`, after the x flip | Positive: the hip is below the shoulder-to-ankle line (toward the floor). Negative: above it. Only the sign is used, so no reference length is needed |

**Which way the patient faces:** the patient faces right when the shoulder is to the right of the ankle in the image (larger x). Otherwise, flip x before measuring (see [Measuring](README.md#measuring)). Decide this on each frame. Only the hip side needs the flip; the other signals are unsigned. Checked with the helpers: after the flip, a sagging hip gives a positive distance whichever way the patient faces. Without the flip, it would be negative for a patient facing left.

## Holds

The patient is **in position** on a frame when all four hold:

| Signal | In position | Rules out |
| --- | --- | --- |
| Body angle | 30° or less | Standing, or kneeling upright |
| Knee angle | 160° or more | Dropping to the knees (most ways, see [Limits](#limits)) |
| Upper-arm angle | 30° or less | Lying flat on the floor with the arms by the sides or overhead |
| Hip angle | 130° or more | Sitting on the floor with straight legs (about 105° to 125°), or the hips raised into an upside-down V |

| Step | Rule | What happens |
| --- | --- | --- |
| Hold starts | The first frame in position | This time is `start_seconds` |
| Hold goes on | Out of position, or not tracked, for 1 second or less | Nothing. A short wobble does not break the hold |
| Hold ends | Out of position, or not tracked, for more than 1 second | `end_seconds` is the last frame in position |
| Hold is kept | `end_seconds` minus `start_seconds` is 2 seconds or more | Shorter holds are dropped, with no issues |

- The 1-second rule does the job of the enter and exit thresholds in exercises done in reps: a value that wobbles near a threshold makes short gaps, which do not end the hold.
- Dropping to the knees, standing up, or lying flat ends a hold. Sagging or raised hips do not (unless the hip angle falls below 130°): they are form issues inside the hold (see [Reps and holds](../analysis-result.md#reps-and-holds)).
- Lost tracking ends a hold, as above, instead of dropping it. This replaces the rule for reps in [Measuring](README.md#measuring).
- If the video ends during a hold, the hold ends at its last frame in position.
- `hold_seconds` is the longest kept hold. The framework sets it.

## Form rules

Checked on every frame used from `start_seconds` to `end_seconds` of each hold. For consecutive video frames at times `t` and `next_t`, the first frame represents `[t, next_t)`. Only the part inside the hold's `[start_seconds, end_seconds)` interval contributes to issue time. Keep untracked frames in the timeline: they contribute no issue time, so a tracked frame never represents the whole tracking gap. The frame at `end_seconds` contributes zero time. An issue is reported for a hold only if its time in that hold is 1 second or more.

For example, 31 frames at 15 fps from 0 through 2 seconds make a 2-second hold, with 30 intervals of 1/15 second. If all frames show sagging hips, the issue time is 2 seconds, good-form time is 0, and the hold scores 0.

| Code | Rule | Message | Tip | Penalty |
| --- | --- | --- | --- | --- |
| `hips_sagging` | Hip side is positive (below the line) and hip angle is under 160° | Your hips sagged toward the floor. | Tighten your stomach to keep a straight line from your shoulders to your ankles. | 30 |
| `hips_too_high` | Hip side is negative (above the line) and hip angle is under 160° | Your hips rose too high. | Lower your hips to make a straight line from your shoulders to your ankles. | 10 |

- A hip angle of 160° means the hip is about 0.2 torso lengths off the line, roughly 10 to 12 cm for an adult.
- The rules compare the hip to the line from shoulder to ankle, not to the shoulder's height. In a good forearm plank the hips are lower than the shoulders, because the shoulders are raised on the forearms.
- No `too_fast` rule: a hold has no reps.
- **Good-form time** is the hold's time minus the duration of the union of intervals when a reported issue was present (count overlapping intervals once). Keep it between 0 and the hold's duration, including after floating-point arithmetic. Time with an issue that was not reported (under 1 second) counts as good form, so a hold with no issues scores 100. The framework scores each hold as good-form time divided by hold time (see [Scoring](../analysis-result.md#scoring)). Penalties do not change hold scores. They rank the feedback (see [Feedback](../analysis-result.md#feedback)).

## Metrics

| Name | Meaning |
| --- | --- |
| `good_form_seconds` | Good-form time in this hold (see above). The framework reads it to score the hold |

## Limits

- **The body is three points:** shoulder, hip, and ankle. A rounded back with the hip on the line is not seen, and an arched lower back looks the same as sagging hips.
- **The head and neck** are not checked, so dropping the head or looking up is not seen.
- **No floor is found,** so the analyzer cannot tell whether the knees or the hips touch the floor. Dropping to the knees is seen only through the knee angle. With the toes tucked under, it reads about 153° in a forearm plank and about 134° in a straight-arm plank, so the hold ends. With the shins flat on the floor, it reads about 144° in a straight-arm plank (the hold ends) but about 162° in a forearm plank, which still counts as a plank.
- **Resting on the forearms can look like a plank.** Lying on the forearms with the hips on the floor passes all four in-position checks (its hip angle is about 160°) and reads as a plank. This is why the Camera section says to rest in the start position.
- **The camera must be truly side-on.** All angles are 2D. If the patient turns toward or away from the phone, the angles change, and the hips can look straighter or more bent than they are.
- **Only the near side is measured.** The far arm and leg are not checked.
