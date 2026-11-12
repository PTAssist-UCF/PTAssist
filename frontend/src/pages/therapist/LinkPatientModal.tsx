import { useState, type FormEvent } from 'react';
import { Button, Group, Modal, Stack, TextInput } from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';

import type { LinkedPatientResponse } from '@/api/model';
import { getListLinkedPatientsQueryKey, useLinkPatient } from '@/api/patients';
import { ApiError } from '@/apiClient';
import { apiErrorText } from './apiErrorText';

/**
 * A dialog to link a patient by the email they signed in to PTAssist with
 * (POST /therapist/patients). After a link, the patient list is loaded again.
 */
export default function LinkPatientModal({
  opened,
  onClose,
  onLinked,
}: {
  opened: boolean;
  onClose: () => void;
  onLinked: (patient: LinkedPatientResponse) => void;
}) {
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="Link a patient"
      centered
      // Opens and closes at once, without animation, like the unlink dialog.
      transitionProps={{ duration: 0 }}
    >
      {/* Inside the dialog, so the form starts empty each time it opens. */}
      <LinkPatientForm onCancel={onClose} onLinked={onLinked} />
    </Modal>
  );
}

function LinkPatientForm({
  onCancel,
  onLinked,
}: {
  onCancel: () => void;
  onLinked: (patient: LinkedPatientResponse) => void;
}) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const linkPatient = useLinkPatient({
    mutation: {
      // Here rather than in mutate(), so the list refreshes even if the dialog was closed
      // before the answer came.
      onSuccess: () => queryClient.invalidateQueries({ queryKey: getListLinkedPatientsQueryKey() }),
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // The API ignores case and the spaces around the email, so only a blank one is
    // caught here.
    const trimmed = email.trim();
    if (!trimmed) {
      setError("Enter the patient's email.");
      return;
    }
    linkPatient.mutate(
      { data: { email: trimmed } },
      {
        onSuccess: (patient) => onLinked(patient),
        onError: (err) => setError(linkErrorMessage(err)),
      },
    );
  }

  return (
    <form onSubmit={submit}>
      <Stack>
        <TextInput
          data-autofocus
          type="email"
          // Someone else's email, so the browser shouldn't suggest the therapist's own.
          autoComplete="off"
          label="Patient's email"
          description="The email they signed in to PTAssist with. They must have signed in once."
          value={email}
          onChange={(event) => {
            setEmail(event.currentTarget.value);
            setError(null);
          }}
          error={error}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" color="teal" loading={linkPatient.isPending}>
            Link patient
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

/** What to tell the therapist when linking fails. */
function linkErrorMessage(error: unknown): string {
  // A 422 carries FastAPI's list of field errors, not a sentence: the email was blank,
  // longer than 320 characters, or had a character the API refuses.
  if (error instanceof ApiError && error.status === 422) {
    return 'Check the email address and try again.';
  }
  // The others come with a sentence to show, for example 404 (no patient uses that
  // email) and 409 (already linked, or more than one patient uses that email).
  return apiErrorText(error);
}
