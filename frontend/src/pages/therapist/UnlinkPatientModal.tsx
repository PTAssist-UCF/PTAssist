import { useState } from 'react';
import { Alert, Button, Group, Modal, Stack, Text } from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';

import type { LinkedPatientResponse } from '@/api/model';
import { getListLinkedPatientsQueryKey, useUnlinkPatient } from '@/api/patients';
import { ApiError } from '@/apiClient';
import { apiErrorText } from './apiErrorText';

/**
 * Asks before unlinking a patient (DELETE /therapist/patients/{id}). It is open while
 * `patient` is set. Unlinking removes only the link: the patient keeps their plan,
 * sessions, and results, and linking them again shows all of it again.
 */
export default function UnlinkPatientModal({
  patient,
  onClose,
  onUnlinked,
}: {
  patient: LinkedPatientResponse | null;
  onClose: () => void;
  onUnlinked: (patient: LinkedPatientResponse) => void;
}) {
  return (
    <Modal
      opened={patient !== null}
      onClose={onClose}
      title="Unlink patient?"
      centered
      // Closes at once, without animation: its text needs `patient`, which is cleared
      // when it closes, so a fade-out would show an empty dialog.
      transitionProps={{ duration: 0 }}
    >
      {patient && <ConfirmUnlink patient={patient} onCancel={onClose} onUnlinked={onUnlinked} />}
    </Modal>
  );
}

function ConfirmUnlink({
  patient,
  onCancel,
  onUnlinked,
}: {
  patient: LinkedPatientResponse;
  onCancel: () => void;
  onUnlinked: (patient: LinkedPatientResponse) => void;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const unlinkPatient = useUnlinkPatient({
    mutation: {
      onSettled: async (_data, failure) => {
        const queryKey = getListLinkedPatientsQueryKey();
        // Stop any read of the list still on its way: it may still list the patient.
        await queryClient.cancelQueries({ queryKey });
        // Unlinked (204), or already unlinked (404): take them off the list in the cache
        // now, so they and their last session leave the page even if the reload fails.
        if (!failure || (failure instanceof ApiError && failure.status === 404)) {
          queryClient.setQueryData<LinkedPatientResponse[]>(queryKey, (patients) =>
            patients?.filter((linked) => linked.id !== patient.id),
          );
        }
        // Then load the list again, whatever the answer, without making the dialog wait.
        void queryClient.invalidateQueries({ queryKey });
      },
    },
  });

  return (
    <Stack>
      <Text size="sm">
        <Text span fw={600}>
          {patient.email}
        </Text>{' '}
        will leave your list, and you will no longer see their plan, sessions, or results. Nothing
        is deleted: they keep their plan, and linking them again shows everything again.
      </Text>
      {error && <Alert color="red">{error}</Alert>}
      <Group justify="flex-end">
        <Button variant="default" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          color="red"
          loading={unlinkPatient.isPending}
          onClick={() =>
            unlinkPatient.mutate(
              { patientId: patient.id },
              {
                onSuccess: () => onUnlinked(patient),
                onError: (err) => setError(unlinkErrorMessage(err)),
              },
            )
          }
        >
          Unlink
        </Button>
      </Group>
    </Stack>
  );
}

/** What to tell the therapist when unlinking fails. */
function unlinkErrorMessage(error: unknown): string {
  // The API's 404 ("Patient not found") here means the link is already gone, for example
  // because the patient was unlinked in another tab.
  if (error instanceof ApiError && error.status === 404) {
    return 'This patient is no longer linked to you.';
  }
  return apiErrorText(error);
}
