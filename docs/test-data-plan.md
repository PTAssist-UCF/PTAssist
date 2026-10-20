# Test data plan

How test videos are recorded, labeled, and stored, the volunteer consent note, and the license check of open-source datasets. Written in SCRUM-25. The labeled test set (SCRUM-54) follows this plan, with the clip counts in [Success criteria](success-criteria.md).

The rules, from `AGENTS.md`:

- Synthetic or open-source data only. Never real patient data, and no health information about anyone.
- Videos stay in the team OneDrive folder, never in git. The repo keeps only keypoint JSON made from them.

## Where the data comes from

- **Team members** record themselves acting out each exercise, with good form and with known form errors. This is our synthetic data: healthy adult volunteers, not patients.
- **Other adults** who agree (friends, family) may also volunteer, with the same consent note. Before filming anyone outside the team, check with the course instructor that the note is enough.
- **Open-source datasets** are not needed for the proof of concept (see [Open-source datasets](#open-source-datasets)).

Everyone filmed signs the [consent note](#volunteer-consent-note) first, team members included.

## OneDrive folder

One AI team member creates a folder named `PTAssist test data` in their OneDrive and shares it with the 7 team members only ("Specific people"). Never use public or "Anyone with the link" sharing.

```
PTAssist test data/
  clips/<exercise>/<clip-id>.<ext>   Original files from the phone, never edited
  labels.csv                         One row per clip
  consent/                           One signed consent note per volunteer
```

- **Clip id:** `<exercise>-<volunteer code>-<number>`, for example `squat-v03-02`, volunteer v03's second squat clip. `<exercise>` is the name in the API (`side_leg_raise-v01-01`). Volunteer codes are `v01`, `v02`, and so on. The number has two digits.
- **Files:** rename the phone's file to its clip id and keep its extension (`.mov` or `.mp4`). Renaming is fine; trimming or re-encoding is not.
- **Names** appear only in `consent/`. Each note is saved as `consent/<volunteer code>.pdf` (or a photo) and shows the volunteer's name and code, so no other list of names is needed.
- **Deleting:** if a volunteer asks, delete their clips, their rows in `labels.csv`, and their keypoint files in `ai/tests/fixtures/`. At the end of the project (May 2027), the folder's owner deletes the whole folder.

## labels.csv

One row per clip. [Success criteria](success-criteria.md#labels) says how each true value is counted and who checks it.

| Column | Value |
| --- | --- |
| `clip_id` | For example `squat-v03-02` |
| `exercise` | The name in the API |
| `volunteer` | Volunteer code, for example `v03` |
| `phone` | `iphone` or `android` |
| `true_rep_count` | The true number of reps. Blank for the plank |
| `true_hold_seconds` | Plank only: the longest unbroken hold, to the nearest 0.5 second. Blank for the other exercises |
| `form_errors` | The issue codes the clip shows, separated by `;`. Blank for good form |
| `labeled_by` | First name of the team member who recorded and labeled the clip |
| `checked_by` | First name of the team member who checked it |
| `notes` | The side for `side_leg_raise` and `shoulder_abduction` (`left`, `right`, or `both`), and anything unusual. No names or health information |

```csv
clip_id,exercise,volunteer,phone,true_rep_count,true_hold_seconds,form_errors,labeled_by,checked_by,notes
squat-v03-02,squat,v03,android,5,,not_deep_enough,Jonathan,Carlos,
```

## Recording protocol

### Every clip

- Use the phone's own camera app, normal video mode, at 1080p and 30 fps (the default on most phones). Use the normal 1x lens, not the ultra-wide one. No slow motion, cinematic, portrait, filter, or beauty modes. The front or back camera is fine.
- Put the phone on a stand, or prop it so it cannot move. Do not hold it. Keep it level, not tilted to one side.
- Place it as the exercise's spec says (its Camera section), in portrait or landscape (see the table below).
- Good light from the front or side, not a bright window behind you. A plain background, with no mirror or screen showing people.
- Fitted clothes, so the shoulders, elbows, hips, knees, and ankles can be seen.
- Only the volunteer in the frame. Nothing that identifies anyone, such as ID cards, letters, or name badges. Audio is not used; do not say names while recording.
- The whole body the spec asks for stays in the frame for the whole clip.
- Start recording, get into the spec's start position, and stay still for about 2 seconds. Walking into place after pressing record is fine, as a patient would. End in the start position, still for about 2 seconds, then stop.
- Clips are about 10 to 60 seconds long (the app accepts 3 seconds to 2 minutes).
- 5 reps per clip, slow and steady (about 5 seconds for each full movement), unless the clip is for `too_fast`. For shallow squats and low arm or leg lifts, add a 2-second pause at the bottom of the squat or top of the lift. Plank: one hold of 20 to 40 seconds.
- The analyzer times only the part between the spec's rep-start and rep-end thresholds, not the whole movement from rest. That interval must be at least 2 seconds (3 for cat-cow) on clips that are not for `too_fast`. Shallow movements spend less time between those thresholds, which is why they need the extra pause. The second person checking the clip checks this interval too; slow down and record it again if it is too short rather than adding `too_fast` to its label.
- Act out only the one error the clip is for, on every rep (or for the whole hold). Make it clear, but still do full reps: a half squat, not a small dip.
- Afterwards: watch the clip once to check the framing, rename it to its clip id, upload it to `clips/<exercise>/`, add its row to `labels.csv`, and delete it from the phone and its photo backup.

### Each exercise

| Exercise | Phone | Camera (see the spec) | Sides and direction |
| --- | --- | --- | --- |
| [`squat`](exercises/squat.md) | Portrait | Side view, at hip height, 2 to 3 m away. Head to feet in the frame | Face left in about half the clips, right in the others |
| [`plank`](exercises/plank.md) | Landscape | Side view, on the floor or a low step at hip height, 2 to 3 m away. Head to feet in the frame | Head to the left in about half the clips, right in the others |
| [`side_leg_raise`](exercises/side-leg-raise.md) | Landscape | Front view, on the floor in front of the middle of the body, about 3 m away. Head to feet in the frame, including the top foot at the top of each lift | Left leg lifts in 5 clips, right leg in 5 |
| [`shoulder_abduction`](exercises/shoulder-abduction.md) | Portrait | Front view, at chest height, about 3 m away. Top of the head to the hips in the frame, with room for the hands above the head and at the sides | Left arm, right arm, and both arms, at least 3 clips each |
| [`cat_cow`](exercises/cat-cow.md) | Landscape | Side view, on the floor or a low step, at hip height if possible, 2 to 3 m away. Head to knees and feet in the frame | Face left in about half the clips, right in the others |

How to act out each kind of clip. The codes are from each spec's Form rules, and the number of clips of each is in [Success criteria](success-criteria.md#how-many-clips).

| Exercise | Clip | How to act it out |
| --- | --- | --- |
| `squat` | Good form | Squat until your thighs are close to level with the floor, chest up, about 5 seconds per rep |
| | `leaning_forward` | Lean your chest far forward as you go down, so it comes over your knees |
| | `not_deep_enough` | Half squats: stop about halfway between standing and thighs level |
| | `too_fast` | Good squats, but down and up in about 1 second |
| `plank` | Good form | A straight line from shoulders to ankles. In 2 of the 4 clips, hold about 15 seconds, rest on your hands and knees for about 5 seconds, then hold again for about 25 seconds |
| | `hips_sagging` | Let your hips sink about a hand's width below the straight line, without touching the floor |
| | `hips_too_high` | Push your hips up about a hand's width above the straight line (a low upside-down V, not a high one) |
| `side_leg_raise` | Good form | Lift the straight top leg to about 45 degrees, upper body still |
| | `leg_not_high_enough` | Lift only to about 30 degrees |
| | `torso_moves` | Lift your upper body off your bottom arm as your leg goes up |
| | `too_fast` | Good lifts, but up and down in about 1 second |
| `shoulder_abduction` | Good form | Lift to shoulder height or higher, elbow straight, body upright |
| | `torso_lean` | Lean your upper body clearly to one side as you lift |
| | `arm_not_high_enough` | Stop with your hand about 8 inches (20 cm) below shoulder height |
| | `elbow_bent` | Bend your elbow to about a right angle as you lift, hand pointing up (not forward toward the phone) |
| | `too_fast` | Good lifts, but up and down in about 1 second |
| `cat_cow` | Good form | A full cat (back rounded, chin tucked) and a full cow (belly down, head up), about 5 seconds per rep |
| | `small_movement` | Make the cat and the cow clearly smaller than your full ones, but still tuck your chin and lift your head |
| | `arms_bent` | Keep your elbows bent the whole time, pointing back toward your knees (not out to the side) |
| | `hips_rock` | Rock your hips forward over your hands in the cow, and back toward your heels in the cat |
| | `too_fast` | Good reps, but each cat and cow in about 2 seconds |

## Volunteer consent note

Print it, or copy it into a document, for each volunteer. Sign it on paper or electronically, and save it as `consent/<volunteer code>.pdf` or a photo. Give each new volunteer the next free code.

> **PTAssist test video consent**
>
> PTAssist is a student project at the University of Central Florida (UCF) that checks home exercise videos. I agree to be filmed doing exercises to test it.
>
> - **What is recorded:** videos of me exercising. My face may be visible.
> - **Who sees them:** only the 7 PTAssist team members.
> - **What may be shared:** body-position numbers (keypoints) made from the videos may go in the project's public GitHub repository. They are not pictures and do not include my name.
> - **How long:** the videos are deleted by May 2027, when the project ends.
> - **My choice:** taking part is voluntary. I can ask for my videos to be deleted at any time. Published keypoints may stay in the repository's history.
> - **Not medical care:** no medical advice is given. I do only comfortable movements and can stop at any time.
> - I am 18 or older.
>
> Name: ____________ Signature: ____________ Date: ________ Volunteer code: ______

## Keypoint JSON for tests

SCRUM-54 commits keypoint JSON made from each clip into `ai/tests/fixtures/`, never the video. Make it with the keypoint prototype (SCRUM-27, see `ai/README.md`, Keypoint prototype). From `ai/`:

```bash
python -m app.keypoints ~/Downloads/squat-v03-02.mov --out ~/ptassist-keypoints
```

It writes `squat-v03-02.keypoints.json` and `squat-v03-02.overlay.mp4`, named after the video, so download the clip under its clip id.

- Copy only the JSON into `ai/tests/fixtures/`, and keep its name (`<clip-id>.keypoints.json`).
- Never use `ai/tests/fixtures/` as the `--out` folder. Git ignores `.mp4` files everywhere except there, so the overlay, which shows the volunteer, could be committed.
- Before committing, open the JSON and check that it holds only `video`, `model`, and `frames`: no file path and no names.
- Delete the downloaded video and the overlay when done.

## Open-source datasets

Checked in October 2026. Most license names come from search results rather than the official page, so read the official page before using any source.

| Source | Our exercises in it | License | Testing in our OneDrive? |
| --- | --- | --- | --- |
| [MM-Fit](https://github.com/KDMStromback/mm-fit) | Squat, and a dumbbell side raise (close to shoulder abduction). Fixed room cameras | Videos: CC BY 4.0 ([1](https://zenodo.org/records/7672767), [2](https://zenodo.org/records/7607736)). Code: MIT | Yes, with credit |
| [REHAB24-6](https://zenodo.org/records/13305826) | Arm abduction and squat, with reps labeled correct or incorrect by a physiotherapist | CC BY-NC 4.0, non-commercial research only | Yes, non-commercial |
| [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Squat_-_exercise_demonstration_video.webm) | Squat only | Per file. The linked squat clip is CC BY 3.0 | Yes, with credit |
| [Mendeley "Seven Fitness Exercises"](https://data.mendeley.com/datasets/kgbb3yn47p/3), REHAB26-ViewAngles | Squat (phone video) | Not confirmed: official page not read, or no license found | No, until someone reads the license |
| [Fitness-AQA](https://github.com/ParitoshParmar/Fitness-AQA) | Barbell back squat only | CC BY-NC 4.0, plus terms: no sharing outside the team, protect faces | Only after an access request. Poor fit |
| [QEVD](https://www.qualcomm.com/developer/software/qevd-dataset) | 148 exercises, not checked one by one | [Qualcomm Data Research License](https://www.qualcomm.com/content/dam/qcomm-martech/dm-assets/documents/Dataset-Research-License-Feb-25-2025.pdf): internal, non-profit research | Only after accepting the license |
| [Fit3D](https://fit3d.imar.ro/), [EgoExo-Fitness](https://github.com/iSEE-Laboratory/EgoExo-Fitness), [NTU RGB+D](https://rose1.ntu.edu.sg/dataset/actionRecognition/), [Human3.6M](https://vision.imar.ro/human3.6m/eula.php) | Few or none. Lab or studio cameras | Research-only agreements, with registration or a professor's signature | No: paperwork for little fit |
| From YouTube: [Kinetics](https://www.deepmind.com/open-source/kinetics), [Countix](https://arxiv.org/abs/2006.15418), [RepCount](https://svip-lab.github.io/dataset/RepCount_dataset.html), [Penn Action](https://service.tib.eu/ldmservice/dataset/penn-action), [UCF101](https://www.crcv.ucf.edu/research/data-sets/ucf101/), [Kaggle workout videos](https://www.kaggle.com/datasets/hasyimabdillah/workoutfitness-video) | Mostly squat | The labels may be open, but the videos belong to their YouTube uploaders | No |
| Stock video: [Pexels](https://www.pexels.com/license/), [Pixabay](https://pixabay.com/service/license-summary/), [Mixkit](https://mixkit.co/license/) | Some of ours, staged, often with several people | Free to use, but clips may not be shared on their own | Yes |
| [tfjs-models assets](https://github.com/tensorflow/tfjs-models/blob/master/pose-detection/assets/README.md) | None. A dance clip, used to check the keypoint prototype | The repo is Apache 2.0, but its media came from Pexels, so Pexels terms apply | Yes |

**Decision:** not needed for the proof of concept. No dataset with a clear license has the plank, side-lying leg raise, or cat-cow, and none is filmed the way our specs say, so the targets are measured only on our own clips. Never commit any dataset's videos to the repo. If extra squat or shoulder abduction clips are wanted later, REHAB24-6 and MM-Fit are the ones to use, kept in OneDrive with their license.

## To finish SCRUM-25

The task is done when this plan is in `docs/` and at least 1 clip per exercise is in OneDrive. That needs people:

1. One AI team member creates and shares the OneDrive folder, with `clips/`, `consent/`, and a `labels.csv` holding the header row.
2. Each volunteer signs the consent note.
3. The AI team records at least 1 clip per exercise with this protocol, uploads it, and adds its row to `labels.csv`. A second AI team member checks each one.

Clips recorded this way count toward the 50 in SCRUM-54.
