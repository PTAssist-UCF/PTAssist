# Success criteria

The accuracy targets each exercise analyzer must meet, how they are measured, and how many test clips that needs. Written in SCRUM-111.

- The labeled test set (SCRUM-54) is recorded to this page's clip counts, following the [test data plan](test-data-plan.md).
- The evaluation script (SCRUM-72) computes both numbers for each exercise, from `labels.csv` and the analyzer's results.
- The analyzers are tuned to meet them in Sprints 3 and 4 (see [Exercise specs](exercises/README.md)).

## Targets

| Target | What it checks | Goal, for each exercise |
| --- | --- | --- |
| Count accuracy | How close the rep count (plank: the hold time) is to the true one | At least 90% |
| Form agreement | How often the form errors found in a clip match the ones it shows | At least 80% |

The goals are the sponsor's suggested targets: rep counting at least 90% accurate, and form assessment in at least 80% agreement with manually labeled examples. How they are measured is the team's proposal.

All 5 exercises use the same two targets, measured the same way, so one evaluation script covers them. Each exercise must meet both targets on its own clips. They are not averaged across exercises.

## Count accuracy

For each exercise, over all its clips:

```
count accuracy = 1 - (sum over clips of |counted - true|) / (sum over clips of true)
```

- `counted` is `rep_count` in the analyzer's result. `true` is the labeled count (`true_rep_count`).
- Plank: the same formula on seconds. `counted` is `hold_seconds` (the longest hold), and `true` is the labeled longest hold (`true_hold_seconds`).
- A failed result counts as 0.
- Example: 10 clips with 50 true reps. The analyzer misses 3 reps and counts 1 extra: 1 - 4/50 = 92%.
- Each clip's difference is made positive before adding, so a missed rep in one clip and an extra rep in another do not cancel. Inside one clip they do, because labels have no rep times. This is accepted for the proof of concept.

## Form agreement

Checked clip by clip, for each exercise:

- **The label** is the set of issue codes the clip deliberately shows. Each clip acts out one form error or none, so the label is one code, or empty for good form. The codes are the ones in the exercise's spec (Form rules), `too_fast` included.
- **The analyzer's set** is the codes it reported on at least half of its reps: 3 of 5, or 2 of 4. For the plank, the codes on the longest hold.
- **A clip agrees** when the two sets are equal. A clip with a failed result, or with no rep (or no hold) found, does not agree.

```
form agreement = agreeing clips / all clips
```

With 10 clips, at least 8 must agree.

Example: a squat clip labeled `not_deep_enough`. The analyzer counts 5 reps, with `not_deep_enough` on 4 of them and `leaning_forward` on 1. Its set is `not_deep_enough`, so the clip agrees. With `leaning_forward` on 3 reps, its set would have both codes, and the clip would not agree.

- **Half the reps, not all:** one stray issue on one rep should not fail a clip, and an error acted out on every rep should show on most of them.
- **By clip, not by rep:** the person recording knows which error they acted out, so nobody has to judge each rep.
- **Scores are not compared.** They follow from the issues by the shared formula (see [Scoring](analysis-result.md#scoring)).

## Labels

### True values

- **A true rep** is one full movement as the exercise's spec describes it (down and up, lift and lower, or one cat and one cow), counted by a person watching. Both arms lifted together is one rep (`side: "both"`). A rep that acts out an error still counts if it is a full movement: a half squat counts.
- **A true hold** is the plank's longest unbroken hold: from the moment the knees leave the floor with the legs straight, to the moment they start to drop, to the nearest 0.5 second.
- **A true form error** is the one the clip was recorded to show (see [Recording protocol](test-data-plan.md#recording-protocol)).

### Who labels

1. The person who records a clip writes its true count (or hold time) and the error they acted out in `labels.csv` (see [labels.csv](test-data-plan.md#labelscsv)).
2. A second AI team member watches the clip and checks both. If the clip shows another error by mistake (for example, a good-form squat that is clearly shallow), record it again instead of changing its label, so the clip mix stays as planned.
3. If they disagree, a third AI team member decides.

Labels are judged by eye, not measured. The analyzers' thresholds are tuned to match what a person watching sees.

## How many clips

**10 clips per exercise, 50 in total.** SCRUM-54 asks for at least 6.

- Exercises done in reps: 5 reps per clip, so about 50 reps per exercise. One miscounted rep moves count accuracy by 2 points.
- Plank: holds of 20 to 40 seconds, about 300 seconds in total.
- 4 good-form clips per exercise, and 6 clips that each act out one form error, split as evenly as possible across the exercise's codes. When they do not split evenly, the codes listed first in the spec's Form rules get 2 clips. `too_fast` is always listed last.
- At least 3 different people per exercise, and at least one clip from an iPhone and one from an Android phone.
- Sides and directions:
  - Side views (`squat`, `plank`, `cat_cow`): the volunteer faces left in about half the clips and right in the others, so the spec's x flip is tested.
  - `side_leg_raise`: the left leg lifts in 5 clips and the right leg in 5. Lying on the other side also puts the head at the other end.
  - `shoulder_abduction`: at least 3 clips each with the left arm, the right arm, and both arms.

| Exercise | Counted | Form errors labeled | Clip mix |
| --- | --- | --- | --- |
| `squat` | Reps | `leaning_forward`, `not_deep_enough`, `too_fast` | 4 good form, 2 of each error |
| `plank` | Longest hold, in seconds | `hips_sagging`, `hips_too_high` | 4 good form (2 of them with a break: drop to the knees, rest, plank again), 3 of each error |
| `side_leg_raise` | Reps | `leg_not_high_enough`, `torso_moves`, `too_fast` | 4 good form, 2 of each error |
| `shoulder_abduction` | Reps | `torso_lean`, `arm_not_high_enough`, `elbow_bent`, `too_fast` | 4 good form, 2 `torso_lean`, 2 `arm_not_high_enough`, 1 `elbow_bent`, 1 `too_fast` |
| `cat_cow` | Reps | `small_movement`, `arms_bent`, `hips_rock`, `too_fast` | 4 good form, 2 `small_movement`, 2 `arms_bent`, 1 `hips_rock`, 1 `too_fast` |

The plank has no `too_fast`, because a hold has no reps.

### How precise this is

- With 10 clips, 80% means 8 of 10 clips agree. If 8 of 10 agree, the true agreement could plausibly be anywhere from about 50% to 95% (a 95% confidence interval). Telling 80% apart from 70% reliably would take over 100 clips per exercise.
- Count accuracy rests on about 50 reps (or 300 seconds) per exercise, so it is steadier. But the reps in one clip come from one person and one camera setup, so they are not independent.
- The analyzers are tuned on these same clips, so their results here will look better than on new clips. The evaluation report says so.
- This is enough for a proof of concept: it shows whether each analyzer roughly works, and which errors it misses. If a result sits near a target (for example 7 or 8 clips of 10, or count accuracy between 85% and 95%), record more clips for that exercise in Sprint 4.

## Sending to the sponsor

These criteria are a proposal to Dr. Rahaman. The AI team agrees on them first, as the Jira task asks, then sends this page to Dr. Rahaman. If the sponsor wants other targets or more clips, change this page and the [test data plan](test-data-plan.md) before the test set is recorded (SCRUM-54).
