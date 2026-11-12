import { useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Checkbox,
  Container,
  Group,
  Loader,
  NumberInput,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';

import { useListExercises } from '@/api/exercises';
import { useListLinkedPatients } from '@/api/patients';
import { getGetPatientPlanQueryKey, useGetPatientPlan, useSavePatientPlan } from '@/api/plans';
import type { ExerciseResponse, PlanResponse, SavePlanRequest } from '@/api/model';
import { ApiError } from '@/apiClient';
import { apiErrorDetail, describeApiError } from '@/utils/apiErrors';
import { MAX_VIDEO_SECONDS } from '@/utils/videoValidation';

/**
 * The highest target the backend accepts for each field (the lowest is always 1). Copied
 * from backend/app/schemas/plan.py: change them together. They catch typos (100 instead
 * of 10); they are not clinical advice. The backend checks them again on save.
 */
const LIMITS = {
  reps: 100,
  // One video is one set, so a hold has to fit in one clip.
  holdSeconds: MAX_VIDEO_SECONDS,
  sets: 10,
  timesPerWeek: 7,
};

/**
 * The two 404 answers to GET /therapist/patients/{patient_id}/plan, word for word from
 * backend/app/routes/plans.py: change them together. The first means the form starts
 * empty. The second means the therapist may not see the plan: the patient isn't linked
 * to them, or the user is no longer a patient (they can still be in the patient list).
 */
const NO_PLAN_YET = 'This patient has no plan yet';
const PATIENT_NOT_FOUND = 'Patient not found';

type PlanNotFound = 'no plan yet' | 'patient not found';

/** What the form holds for one exercise of the library. An empty field is ''. */
interface ExerciseRow {
  selected: boolean;
  /** Reps per set, or the hold time in seconds for an exercise held for time. */
  target: number | string;
  sets: number | string;
  timesPerWeek: number | string;
}

/** The form's rows, by exercise id. */
type Rows = Record<string, ExerciseRow>;

interface RowErrors {
  target?: string;
  sets?: string;
  timesPerWeek?: string;
}

interface PlanErrors {
  /** True when no exercise is picked: a plan needs at least one. */
  noExercise: boolean;
  /** The field errors of each picked exercise, by exercise id. */
  rows: Record<string, RowErrors>;
  any: boolean;
}

/**
 * The plan builder for one linked patient (/therapist/patients/:patientId/plan): pick
 * exercises from the library, set their targets, and save the whole plan.
 *
 * The rules behind the plan endpoints are in backend/README.md, Exercise library and
 * plans (SCRUM-63).
 */
export default function PlanBuilderPage() {
  const { patientId = '' } = useParams();
  const patients = useListLinkedPatients();
  const exercises = useListExercises();
  const patient = patients.data?.find((linked) => linked.id === patientId);
  // Asks for the plan only once the patient is known to be linked, so an address with an
  // unknown id sends no plan request.
  const plan = useGetPatientPlan(patientId, { query: { enabled: patient !== undefined } });

  // The plan's 404 answer, if it got one. While a refetch runs, a query with no plan data
  // has no error either (for example when the therapist comes back to the tab), so the
  // last 404 for this patient is kept until a plan arrives. Without it, the form of a
  // first plan, and the targets typed in it, would be replaced by a spinner.
  const answered = planNotFound(plan.error);
  const [last404, setLast404] = useState<{ patientId: string; notFound: PlanNotFound }>();
  if (answered && (last404?.patientId !== patientId || last404.notFound !== answered)) {
    setLast404({ patientId, notFound: answered });
  }
  const notFound =
    answered ?? (last404?.patientId === patientId && !plan.data ? last404.notFound : undefined);

  // An error matters only while there is nothing to show. Once the page has loaded, a
  // failed refetch in the background keeps the page, and the changes in the form.
  if (!patients.data || !exercises.data) {
    const error = patients.error ?? exercises.error;
    return error ? <LoadError title="Couldn't load the plan builder" error={error} /> : <Loading />;
  }
  // Checked before any plan is shown, even one from the cache: an id that isn't one of
  // the therapist's patients, or a plan the API won't show them any more.
  if (!patient || notFound === 'patient not found') {
    return (
      <Container size="md" py="md">
        <Alert color="yellow" title="Patient not found">
          You can&apos;t see or change this patient&apos;s plan.{' '}
          <Anchor component={Link} to="/therapist/plans" size="sm">
            Choose one of your patients
          </Anchor>
          .
        </Alert>
      </Container>
    );
  }
  // Only the "no plan yet" answer starts an empty form; any other error is shown.
  if (!plan.data && notFound !== 'no plan yet') {
    return plan.error ? (
      <LoadError title="Couldn't load the plan" error={plan.error} />
    ) : (
      <Loading />
    );
  }

  return (
    <Container size="md" py="md">
      <Stack gap="lg">
        <div>
          <Anchor component={Link} to="/therapist/plans" size="sm">
            Choose another patient
          </Anchor>
          {/* Long emails have no spaces to wrap at, so they may break anywhere. */}
          <Title order={2} size="h3" mt="xs" style={{ overflowWrap: 'anywhere' }}>
            Plan for {patient.email}
          </Title>
          <Text c="dimmed" size="sm">
            Pick exercises from the library and set a target for each. After you save, the patient
            sees the plan on their My Plan page.
          </Text>
        </div>
        {/* Keyed by patient: opening another patient starts a new form, so nothing typed
            for one patient can be saved to another one's plan. */}
        <PlanForm
          key={patientId}
          patientId={patientId}
          exercises={exercises.data}
          plan={plan.data ?? null}
        />
      </Stack>
    </Container>
  );
}

/**
 * The form. It starts from the latest plan (or empty), and never loses the therapist's
 * changes: when a newer plan arrives, a form without changes shows it, and a form with
 * changes keeps them and asks, before saving, which version to keep.
 */
function PlanForm({
  patientId,
  exercises,
  plan,
}: {
  patientId: string;
  exercises: ExerciseResponse[];
  /** The latest plan, or null when the patient has none yet. */
  plan: PlanResponse | null;
}) {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState(() => rowsFromPlan(exercises, plan));
  // The plan the rows started from, or were last brought up to date with.
  const [basePlan, setBasePlan] = useState(plan);
  // Errors show only after the first try to save, then update as the fields change.
  const [showErrors, setShowErrors] = useState(false);
  const save = useSavePatientPlan({
    mutation: {
      onSuccess: async (saved) => {
        const queryKey = getGetPatientPlanQueryKey(patientId);
        // A refetch that started before the save would answer with the old plan, and the
        // form would then show it: cancel it first.
        await queryClient.cancelQueries({ queryKey });
        // The answer is the saved plan: keep it, so pages that read it show it at once.
        queryClient.setQueryData(queryKey, saved);
      },
    },
  });

  // A newer plan arrived: a refetch after another therapist saved it (the cached plan
  // shows first), or this form's own save. Compared by content, not by object.
  const draft = contentOf(exercises, rows);
  const base = contentOf(exercises, rowsFromPlan(exercises, basePlan));
  const latest = contentOf(exercises, rowsFromPlan(exercises, plan));
  if (latest !== base) {
    if (draft === latest) {
      setBasePlan(plan); // the form shows it already, for example after its own save
    } else if (draft === base) {
      // No changes in the form: show the newer plan.
      setRows(rowsFromPlan(exercises, plan));
      setBasePlan(plan);
    }
    // Otherwise the form has changes: they stay, and the therapist chooses below.
  }
  // Still true here only when the form has changes and a newer plan arrived. Saving
  // would then replace the newer plan with an older list, so it waits for a choice.
  const conflict = latest !== base;
  const errors = checkRows(exercises, rows);

  const changeRow = (exerciseId: string, change: Partial<ExerciseRow>) => {
    save.reset(); // a new change hides the message of the last save
    setRows((current) => ({ ...current, [exerciseId]: { ...current[exerciseId], ...change } }));
  };

  // The two answers to a conflict.
  const loadNewerPlan = () => {
    save.reset();
    setShowErrors(false);
    setRows(rowsFromPlan(exercises, plan));
    setBasePlan(plan);
  };
  const keepChanges = () => setBasePlan(plan);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (conflict) {
      return; // the Save button is disabled too; this covers pressing Enter in a field
    }
    if (errors.any) {
      setShowErrors(true);
      return;
    }
    // The whole plan in one request: it creates the plan, or replaces its exercises.
    save.mutate({ patientId, data: toSaveRequest(exercises, rows) });
  };

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Stack gap="md">
        {plan === null ? (
          <Alert color="blue" title="No plan yet">
            This patient has no plan yet. Pick at least one exercise, then save to assign it.
          </Alert>
        ) : (
          <Text size="sm" c="dimmed">
            Exercises the patient has uploaded videos for can&apos;t be removed from the plan, but
            you can change their targets.
          </Text>
        )}

        {exercises.map((exercise) => (
          <ExerciseTargets
            key={exercise.id}
            exercise={exercise}
            row={rows[exercise.id]}
            errors={showErrors ? errors.rows[exercise.id] : undefined}
            disabled={save.isPending}
            onChange={(change) => changeRow(exercise.id, change)}
          />
        ))}

        {showErrors && errors.noExercise && (
          <Alert color="red">Pick at least one exercise for the plan.</Alert>
        )}
        {showErrors && errors.any && !errors.noExercise && (
          <Alert color="red">Check the highlighted targets, then save again.</Alert>
        )}
        {save.isError && <SaveError error={save.error} />}
        {save.isSuccess && (
          <Alert color="teal" title="Plan saved">
            The patient sees this plan on their My Plan page.
          </Alert>
        )}
        {conflict && (
          <Alert color="yellow" title="This plan changed while you were editing it">
            <Text size="sm">
              A newer version was saved, for example by another of this patient&apos;s therapists.
              Load it to start again from it, or keep your changes: saving them replaces the newer
              version.
            </Text>
            <Group gap="sm" mt="sm">
              <Button size="xs" variant="default" onClick={loadNewerPlan}>
                Load the newer version
              </Button>
              <Button size="xs" variant="default" onClick={keepChanges}>
                Keep my changes
              </Button>
            </Group>
          </Alert>
        )}

        <Group justify="flex-end">
          <Button type="submit" color="teal" loading={save.isPending} disabled={conflict}>
            Save plan
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

/** One exercise of the library: a checkbox to put it in the plan, then its targets. */
function ExerciseTargets({
  exercise,
  row,
  errors,
  disabled,
  onChange,
}: {
  exercise: ExerciseResponse;
  row: ExerciseRow;
  errors: RowErrors | undefined;
  disabled: boolean;
  onChange: (change: Partial<ExerciseRow>) => void;
}) {
  const isHold = exercise.kind === 'hold';
  // A side leg raise's reps count both sides together, like the rep count of its results
  // (backend/README.md, Data model).
  const repsHint =
    exercise.name === 'side_leg_raise'
      ? `Both sides together, 1 to ${LIMITS.reps}`
      : `1 to ${LIMITS.reps}`;

  return (
    <Paper withBorder p="md" radius="md" role="group" aria-label={exercise.display_name}>
      <Group justify="space-between" wrap="nowrap">
        <Checkbox
          label={exercise.display_name}
          checked={row.selected}
          disabled={disabled}
          onChange={(event) => onChange({ selected: event.currentTarget.checked })}
          styles={{ label: { fontWeight: 600 } }}
        />
        <Badge variant="light" color={isHold ? 'grape' : 'blue'}>
          {isHold ? 'Held for time' : 'Done in reps'}
        </Badge>
      </Group>

      {row.selected && (
        <SimpleGrid cols={{ base: 1, sm: 3 }} mt="md">
          <TargetInput
            label={isHold ? 'Hold time (seconds)' : 'Reps per set'}
            description={
              isHold ? `1 to ${LIMITS.holdSeconds} seconds, to fit in one video` : repsHint
            }
            max={isHold ? LIMITS.holdSeconds : LIMITS.reps}
            value={row.target}
            error={errors?.target}
            disabled={disabled}
            onChange={(target) => onChange({ target })}
          />
          <TargetInput
            label="Sets"
            description={`One video per set, 1 to ${LIMITS.sets}`}
            max={LIMITS.sets}
            value={row.sets}
            error={errors?.sets}
            disabled={disabled}
            onChange={(sets) => onChange({ sets })}
          />
          <TargetInput
            label="Times per week"
            description={`Days a week, 1 to ${LIMITS.timesPerWeek}`}
            max={LIMITS.timesPerWeek}
            value={row.timesPerWeek}
            error={errors?.timesPerWeek}
            disabled={disabled}
            onChange={(timesPerWeek) => onChange({ timesPerWeek })}
          />
        </SimpleGrid>
      )}
    </Paper>
  );
}

/** A whole-number field from 1 to max. */
function TargetInput({
  label,
  description,
  max,
  value,
  error,
  disabled,
  onChange,
}: {
  label: string;
  description: string;
  max: number;
  value: number | string;
  error: string | undefined;
  disabled: boolean;
  onChange: (value: number | string) => void;
}) {
  return (
    <NumberInput
      label={label}
      description={description}
      value={value}
      onChange={onChange}
      error={error}
      disabled={disabled}
      min={1}
      max={max}
      allowDecimal={false}
      allowNegative={false}
      // No clamping: a typo such as 150 stays visible and gets an error, instead of
      // quietly becoming the limit.
      clampBehavior="none"
    />
  );
}

function SaveError({ error }: { error: Error }) {
  const { title, message, extra } = describeSaveError(error);
  return (
    <Alert color="red" title={title}>
      <Text size="sm">{message}</Text>
      {extra && (
        <Text size="sm" mt="xs">
          {extra}
        </Text>
      )}
    </Alert>
  );
}

function Loading() {
  return (
    <Group justify="center" gap="sm" py="xl">
      <Loader size="sm" />
      <Text c="dimmed">Loading the plan…</Text>
    </Group>
  );
}

function LoadError({ title, error }: { title: string; error: Error }) {
  return (
    <Container size="md" py="md">
      <Alert color="red" title={title}>
        {describeApiError(error)}
      </Alert>
    </Container>
  );
}

/** The form's starting rows: the saved plan's exercises are picked, with their targets. */
function rowsFromPlan(exercises: ExerciseResponse[], plan: PlanResponse | null): Rows {
  const rows: Rows = {};
  for (const exercise of exercises) {
    const saved = plan?.exercises.find((item) => item.exercise.id === exercise.id);
    rows[exercise.id] = saved
      ? {
          selected: true,
          target: (exercise.kind === 'hold' ? saved.hold_seconds : saved.reps) ?? '',
          sets: saved.sets,
          timesPerWeek: saved.times_per_week,
        }
      : { selected: false, target: '', sets: '', timesPerWeek: '' };
  }
  return rows;
}

/**
 * What the rows ask for, as text that is easy to compare: each picked exercise with its
 * targets. Values typed for an exercise that isn't picked don't count.
 */
function contentOf(exercises: ExerciseResponse[], rows: Rows): string {
  return JSON.stringify(
    exercises
      .filter((exercise) => rows[exercise.id].selected)
      .map((exercise) => {
        const { target, sets, timesPerWeek } = rows[exercise.id];
        return [exercise.id, target, sets, timesPerWeek];
      }),
  );
}

/** Which of the plan request's two 404 answers this error is, if it is one of them. */
function planNotFound(error: Error | null): PlanNotFound | undefined {
  if (!(error instanceof ApiError) || error.status !== 404) {
    return undefined;
  }
  const detail = apiErrorDetail(error);
  if (detail === NO_PLAN_YET) {
    return 'no plan yet';
  }
  if (detail === PATIENT_NOT_FOUND) {
    return 'patient not found';
  }
  return undefined; // another 404, for example from a proxy: shown as an error
}

/** The same rules the backend checks: at least one exercise, and every target in range. */
function checkRows(exercises: ExerciseResponse[], rows: Rows): PlanErrors {
  const picked = exercises.filter((exercise) => rows[exercise.id].selected);
  const errors: PlanErrors = { noExercise: picked.length === 0, rows: {}, any: false };
  for (const exercise of picked) {
    const row = rows[exercise.id];
    const rowErrors: RowErrors = {
      target: checkRange(row.target, exercise.kind === 'hold' ? LIMITS.holdSeconds : LIMITS.reps),
      sets: checkRange(row.sets, LIMITS.sets),
      timesPerWeek: checkRange(row.timesPerWeek, LIMITS.timesPerWeek),
    };
    errors.rows[exercise.id] = rowErrors;
    if (rowErrors.target || rowErrors.sets || rowErrors.timesPerWeek) {
      errors.any = true;
    }
  }
  errors.any ||= errors.noExercise;
  return errors;
}

/** An error message, unless the value is a whole number from 1 to max. */
function checkRange(value: number | string, max: number): string | undefined {
  const valid = typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= max;
  return valid ? undefined : `Enter a whole number from 1 to ${max}.`;
}

/**
 * The body of the save: every picked exercise, with the target its kind needs (reps, or
 * hold_seconds for an exercise held for time). Call it only once checkRows finds no errors.
 */
function toSaveRequest(exercises: ExerciseResponse[], rows: Rows): SavePlanRequest {
  return {
    exercises: exercises
      .filter((exercise) => rows[exercise.id].selected)
      .map((exercise) => {
        const row = rows[exercise.id];
        const target = Number(row.target);
        return {
          exercise_id: exercise.id,
          ...(exercise.kind === 'hold' ? { hold_seconds: target } : { reps: target }),
          sets: Number(row.sets),
          times_per_week: Number(row.timesPerWeek),
        };
      }),
  };
}

/** What to tell the therapist when a save fails. Nothing is saved in any of these cases. */
function describeSaveError(error: Error): { title: string; message: string; extra?: string } {
  const status = error instanceof ApiError ? error.status : undefined;
  const detail = apiErrorDetail(error);
  if (status === 409) {
    // An exercise left out of the plan has uploaded videos. Their results are kept, so
    // the backend refuses to remove it. Its sentence names the exercises.
    return {
      title: "Some exercises can't be removed from the plan",
      message:
        detail ??
        "Nothing was saved. The patient has uploaded videos for an exercise you took out, so it can't be removed.",
      extra: 'Pick those exercises again to keep them in the plan, then save.',
    };
  }
  if (status === 404) {
    return {
      title: 'Patient not found',
      message: 'Nothing was saved. This patient is no longer linked to you.',
    };
  }
  if (status === 422) {
    // A sentence for an unknown exercise or the wrong kind of target. Other 422s have
    // FastAPI's list of field errors, which the checks above should already prevent.
    return {
      title: 'The plan was not saved',
      message: detail ?? "The API didn't accept these targets. Check them and try again.",
    };
  }
  return { title: 'The plan was not saved', message: describeApiError(error) };
}
