# Exercise specs

One spec per exercise: how to film it, which joints matter, what counts as one rep (or when a hold starts and ends), the form rules, and the feedback wording. Written in SCRUM-29.

| Exercise | Name in the API | Kind | Sides | Camera | Spec |
| --- | --- | --- | --- | --- | --- |
| Squat | `squat` | Reps | none | Side view | [`squat.md`](squat.md) |
| Plank | `plank` | Hold | none | Side view, floor level | [`plank.md`](plank.md) |
| Side-lying leg raise | `side_leg_raise` | Reps | left, right | Front view, floor level | [`side-leg-raise.md`](side-leg-raise.md) |
| Shoulder abduction | `shoulder_abduction` | Reps | left, right, both | Front view | [`shoulder-abduction.md`](shoulder-abduction.md) |
| Cat-cow | `cat_cow` | Reps | none | Side view, floor level | [`cat-cow.md`](cat-cow.md) |

Who uses them:

- The exercise analyzers in `ai/app/analysis/exercises/` implement them (SCRUM-51, SCRUM-53, SCRUM-69 to SCRUM-71).
- The labeled test set (SCRUM-54) is filmed with each spec's camera setup and acts out its form errors (see [`../test-data-plan.md`](../test-data-plan.md)). The analyzers are tuned against [`../success-criteria.md`](../success-criteria.md).
- The upload page's recording tips (SCRUM-97) come from each spec's **Camera** section.

How a result is shaped (reps, holds, sides, issues, metrics, scores, and feedback) is in [`../analysis-result.md`](../analysis-result.md). This page adds the rules that every spec shares.

## Rules for every exercise

### Thresholds are starting values

Every number in a spec is an engineering starting value, taken from the AI team's prototype (`Jonathan-AI-Test` branch) where it had one. **None is a clinical target.** They are tuned against the labeled test set in Sprints 3 and 4. Changing a threshold, penalty, or wording changes results, so raise `ANALYZER_VERSION` in `ai/app/main.py` (see [Versions](../analysis-result.md#versions)).

### Measuring

- Analyzers read MediaPipe Pose landmarks by name (`left_knee`, `right_shoulder`, ...) and measure with the shared helpers in `ai/app/analysis/` (see `ai/README.md`, Shared analyzer helpers). All angles are 2D, in the image: one camera cannot measure depth.
- A frame is used only when all of the exercise's **required joints** pass `is_frame_visible` with the defaults: confidence at least 0.65, and inside the frame by at least 2.5% of its size. Other frames are skipped, never guessed.
- Each measured signal is smoothed with its own `ExponentialSmoother()` (0.12 s, gaps up to 0.75 s). All thresholds apply to smoothed values.
- If tracking is lost for more than 0.75 s during a rep, that rep is dropped (not counted), and the analyzer waits for the start position again.
- **Side views** (squat, plank, cat-cow) use the side of the body nearer the camera: the side (`left_...` or `right_...`) whose required joints have the higher lowest confidence. Switch sides only when the other side's lowest confidence is higher by more than 0.12, as in the prototype. A switch keeps the rep in progress: reset the smoothers and go on. If the patient faces left in the image, flip x (`x` becomes `1 - x`) before measuring, so every signed measurement means the same thing whichever way they face. Each spec says how to tell which way they face.

### Reps

- A rep counts only when it is finished: the patient left the start position, reached the spec's **count threshold**, and came back to the start position. Each spec gives separate thresholds for leaving the start position and for coming back to it, a few degrees apart, so noise near one value cannot start or end a rep twice. Once the count threshold is reached, it stays reached until the rep ends.
- A movement that returns to the start position without reaching the count threshold is not a rep, and gets no issues.
- `start_seconds` is when the patient left the start position. `end_seconds` is when they were back in it.
- Form rules are checked over the whole rep, from `start_seconds` to `end_seconds`, usually on the smallest or largest value of a signal during the rep.

### Too fast (every exercise done in reps)

Every exercise done in reps has the same tempo rule. A rep that takes less than the spec's **minimum rep time** (2 seconds unless the spec says otherwise) gets this issue:

| Code | Message | Tip | Penalty |
| --- | --- | --- | --- |
| `too_fast` | This rep took less than 2 seconds. | Slow down: take at least 2 seconds for each rep. | 10 |

When a spec sets another minimum, put its number in both sentences.

### Penalties

Two sizes only, so penalties stay easy to compare across exercises:

- **30 (major):** the movement is clearly done differently from how it should be, for example leaning the chest far forward in a squat.
- **10 (minor):** the movement is right but not complete or not clean, for example not going deep enough or bending an elbow.

Rep and hold scores, and the overall score, are computed from these by the shared framework (see [Scoring](../analysis-result.md#scoring)).

### Wording

- **Message** (what went wrong): one short sentence in the past tense, speaking to the patient: "Your knees moved inward."
- **Tip** (what to do next time, used as the feedback line): one short sentence, starting with a verb: "Keep your chest up."
- Plain words, no medical terms or claims, no blame. Patients and therapists see the same text. The wording is reviewed in SCRUM-90.

### Metrics

Each rep (or hold) reports the metrics in its spec, rounded to 0.1. Each name ends with its unit: `_degrees`, `_seconds`, or `_torso_lengths` (a distance divided by the shoulder-to-hip length).

## Spec template

Each spec uses these sections, in this order:

1. **Summary**: one or two sentences on the movement, then a table with the name in the API, kind (reps or hold), sides, and minimum rep time.
2. **Camera**: where the phone goes, how high, how far, landscape or portrait, what must stay in the frame, and the start position. Written so it can be shown to a patient.
3. **Required joints**: the landmark names that must be visible.
4. **Measurements**: each signal, how it is computed (which helper and which joints), and how to tell which way the patient faces (side views).
5. **Counting reps** (or **Holds**): the start position, each step with its threshold, and when a rep counts or is dropped.
6. **Form rules**: a table with code, rule (the threshold), message, tip, and penalty, including `too_fast`.
7. **Metrics**: a table with name and meaning.
8. **Limits**: what one 2D camera cannot see for this exercise.
