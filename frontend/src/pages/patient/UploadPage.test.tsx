import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

import UploadPage from './UploadPage';
import * as apiClient from '@/apiClient';
import { getGetMyPlanQueryKey } from '@/api/plans';
import type { PlanResponse } from '@/api/model';
import * as videoValidation from '@/utils/videoValidation';
import { NO_PLAN, PLANK, SQUAT, fakePlanApi, planWith } from './testPlan';

vi.mock('@/apiClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/apiClient')>();
  return {
    ...actual,
    uploadWithProgress: vi.fn(),
  };
});

// The upload pages for the exercises of the test plan, as their Record / Upload buttons
// open them.
const SQUAT_UPLOAD = `/patient/upload?plan_exercise_id=${SQUAT.id}`;
const PLANK_UPLOAD = `/patient/upload?plan_exercise_id=${PLANK.id}`;

// What the page says when an upload finds its exercise gone from the plan (404).
const REMOVED =
  "This exercise was removed from your plan, so your video wasn't saved. Please choose an exercise from your plan.";

describe('UploadPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(videoValidation, 'getVideoDuration').mockResolvedValue(15);
    // Every test gets a plan with a squat and a plank. Tests can swap it.
    fakePlanApi([200, planWith(SQUAT, PLANK)]);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  /** Opens the page with this history: the last address is the current one. */
  function renderPage(initialEntries = ['/patient/upload']) {
    // retry: false, so a failed request fails at once instead of being retried.
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // A router whose history the tests can go back in, like the browser's Back button.
    const router = createMemoryRouter(
      [
        { path: '/patient/upload', element: <UploadPage /> },
        { path: '/patient', element: <div>Patient Plan Page</div> },
      ],
      { initialEntries },
    );
    render(
      <QueryClientProvider client={queryClient}>
        <MantineProvider>
          <RouterProvider router={router} />
        </MantineProvider>
      </QueryClientProvider>,
    );
    return { router, queryClient };
  }

  /** The browser's Back button. */
  async function goBack(router: ReturnType<typeof renderPage>['router']) {
    await act(() => router.navigate(-1));
  }

  /** Picks this video in the file input, once the page shows the form. */
  async function chooseVideo(file: File) {
    const fileInput = await screen.findByTestId('file-input');
    fireEvent.change(fileInput, { target: { files: [file] } });
  }

  /** Picks a valid video (its length check gives 15 seconds) and uploads it. */
  async function uploadVideo(name: string) {
    await chooseVideo(new File(['video'], name, { type: 'video/mp4' }));
    expect(await screen.findByText('Duration: 0:15')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Upload Video' }));
  }

  it('shows the exercise from the plan, with no field to type an id into', async () => {
    renderPage([SQUAT_UPLOAD]);

    expect(screen.getByRole('heading', { name: 'Upload Video' })).toBeDefined();
    expect(await screen.findByRole('heading', { name: 'Squat' })).toBeDefined();
    expect(screen.getByText('3 sets × 10 reps')).toBeDefined();
    expect(screen.getByText('3 times a week')).toBeDefined();
    expect(screen.queryByLabelText(/plan exercise id/i)).toBeNull();
    expect(screen.getByRole('button', { name: /record with camera/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /choose video file/i })).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Recording Tips' })).toBeDefined();
  });

  it('configures phone camera capture and desktop file inputs correctly', async () => {
    renderPage([SQUAT_UPLOAD]);

    const cameraInput = (await screen.findByTestId('camera-input')) as HTMLInputElement;
    const fileInput = screen.getByTestId('file-input') as HTMLInputElement;

    expect(cameraInput.type).toBe('file');
    expect(cameraInput.getAttribute('accept')).toBe('video/mp4,video/quicktime,video/webm');
    expect(cameraInput.getAttribute('capture')).toBe('environment');

    expect(fileInput.type).toBe('file');
    expect(fileInput.getAttribute('accept')).toBe('video/mp4,video/quicktime,video/webm');
    expect(fileInput.getAttribute('capture')).toBeNull();
  });

  it("without an exercise in the address, offers the plan's exercises to choose from", async () => {
    renderPage();

    expect(await screen.findByText('Which exercise is this video for?')).toBeDefined();
    expect(screen.getByRole('link', { name: /squat/i }).getAttribute('href')).toBe(SQUAT_UPLOAD);
    const plank = screen.getByRole('link', { name: /plank/i });
    expect(plank.getAttribute('href')).toBe(`/patient/upload?plan_exercise_id=${PLANK.id}`);
    // Nothing to upload until an exercise is chosen.
    expect(screen.queryByTestId('file-input')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Upload Video' })).toBeNull();
    expect(screen.queryByText("This exercise isn't in your plan")).toBeNull();

    fireEvent.click(plank);

    expect(await screen.findByRole('heading', { name: 'Plank' })).toBeDefined();
    expect(screen.getByText('3 sets × 30-second hold')).toBeDefined();
    expect(screen.getByTestId('file-input')).toBeDefined();
  });

  it('says so when the exercise in the address is not in the plan, and offers the plan', async () => {
    renderPage(['/patient/upload?plan_exercise_id=7f0e4c1a-0000-4000-8000-000000000000']);

    expect(await screen.findByText("This exercise isn't in your plan")).toBeDefined();
    expect(screen.getByRole('link', { name: /squat/i })).toBeDefined();
    expect(screen.queryByTestId('file-input')).toBeNull();
  });

  it("says so when the therapist hasn't assigned a plan yet (404)", async () => {
    fakePlanApi([404, NO_PLAN]);

    renderPage([SQUAT_UPLOAD]);

    expect(await screen.findByText("Your therapist hasn't assigned a plan yet")).toBeDefined();
    expect(screen.queryByTestId('file-input')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Upload Video' })).toBeNull();
  });

  it('validates file size on client-side and prevents upload of empty files', async () => {
    renderPage([SQUAT_UPLOAD]);

    await chooseVideo(new File([], 'empty.mp4', { type: 'video/mp4' }));

    expect(await screen.findByText(/couldn't open your video/i)).toBeDefined();
    const uploadButton = screen.getByRole('button', { name: 'Upload Video' });
    expect(uploadButton.hasAttribute('disabled')).toBe(true);
  });

  it('validates file size on client-side and prevents upload of files > 1 GiB', async () => {
    renderPage([SQUAT_UPLOAD]);

    const largeFile = new File(['content'], 'oversized.mp4', { type: 'video/mp4' });
    Object.defineProperty(largeFile, 'size', {
      value: videoValidation.MAX_VIDEO_UPLOAD_BYTES + 10,
    });
    await chooseVideo(largeFile);

    expect(await screen.findByText(/exceeds the 1 GiB limit/i)).toBeDefined();
    const uploadButton = screen.getByRole('button', { name: 'Upload Video' });
    expect(uploadButton.hasAttribute('disabled')).toBe(true);
  });

  it('validates video length on client-side (< 3s)', async () => {
    vi.spyOn(videoValidation, 'getVideoDuration').mockResolvedValue(2.5);
    renderPage([SQUAT_UPLOAD]);

    await chooseVideo(new File(['content'], 'short.mp4', { type: 'video/mp4' }));

    expect(await screen.findByText(/shorter than 3 seconds/i)).toBeDefined();
    const uploadButton = screen.getByRole('button', { name: 'Upload Video' });
    expect(uploadButton.hasAttribute('disabled')).toBe(true);
  });

  it('validates video length on client-side (> 120s)', async () => {
    vi.spyOn(videoValidation, 'getVideoDuration').mockResolvedValue(125);
    renderPage([SQUAT_UPLOAD]);

    await chooseVideo(new File(['content'], 'long.mp4', { type: 'video/mp4' }));

    expect(await screen.findByText(/longer than 2 minutes/i)).toBeDefined();
    const uploadButton = screen.getByRole('button', { name: 'Upload Video' });
    expect(uploadButton.hasAttribute('disabled')).toBe(true);
  });

  it('uploads a valid video for the exercise of the plan, and creates a processing session', async () => {
    const sessionResponse = {
      id: 'd9b3e1a0-5421-4f1b-85c8-111122223333',
      plan_exercise_id: SQUAT.id,
      status: 'processing' as const,
      created_at: new Date().toISOString(),
    };

    let sentPath: string | undefined;
    let sentForm: FormData | undefined;
    let progressCb: ((ev: apiClient.UploadProgressEvent) => void) | undefined;
    vi.mocked(apiClient.uploadWithProgress).mockImplementation((path, data, options) => {
      sentPath = path;
      sentForm = data;
      progressCb = options?.onProgress;
      return new Promise((resolve) => {
        setTimeout(() => {
          progressCb?.({ loaded: 50, total: 100, percent: 50 });
          progressCb?.({ loaded: 100, total: 100, percent: 100 });
          resolve(sessionResponse);
        }, 10);
      });
    });

    renderPage([SQUAT_UPLOAD]);

    const validFile = new File(['valid video content'], 'exercise.mp4', { type: 'video/mp4' });
    await chooseVideo(validFile);

    await waitFor(() => {
      expect(screen.getByText('exercise.mp4')).toBeDefined();
      expect(screen.getByText('Duration: 0:15')).toBeDefined();
    });

    const uploadButton = screen.getByRole('button', { name: 'Upload Video' });
    fireEvent.click(uploadButton);

    // Progress bar shows during upload
    await waitFor(() => {
      expect(screen.getByText(/uploading video/i)).toBeDefined();
    });

    // Success alert shows session id and processing badge
    await waitFor(() => {
      expect(screen.getByText('Upload complete!')).toBeDefined();
      expect(screen.getByText(sessionResponse.id)).toBeDefined();
      expect(screen.getByText('processing')).toBeDefined();
    });

    // The video went to POST /sessions with the plan exercise's id from the plan.
    expect(sentPath).toBe('/sessions');
    expect(sentForm?.get('plan_exercise_id')).toBe(SQUAT.id);
    expect(sentForm?.get('video')).toBeInstanceOf(File);

    // Navigation back to plan
    await waitFor(
      () => {
        expect(screen.getByText('Patient Plan Page')).toBeDefined();
      },
      { timeout: 2500 },
    );
  });

  it('displays API error message when upload fails', async () => {
    vi.mocked(apiClient.uploadWithProgress).mockRejectedValue(
      new apiClient.ApiError(422, { detail: 'Video unreadable' }),
    );

    renderPage([SQUAT_UPLOAD]);

    await chooseVideo(new File(['abc'], 'clip.mp4', { type: 'video/mp4' }));
    await waitFor(() => expect(screen.getByText('clip.mp4')).toBeDefined());

    fireEvent.click(screen.getByRole('button', { name: 'Upload Video' }));

    expect(await screen.findByText('Video unreadable')).toBeDefined();
    expect(screen.getByText('Upload failed')).toBeDefined();
  });

  it('says so when the exercise left the plan during the upload (409), and loads the plan again', async () => {
    // The therapist takes the squat out of the plan while the video uploads.
    const api = fakePlanApi([200, planWith(SQUAT, PLANK)], [200, planWith(PLANK)]);
    const detail =
      "This exercise was removed from your plan while your video was uploading, so the video wasn't saved. Please refresh your plan.";
    vi.mocked(apiClient.uploadWithProgress).mockRejectedValue(
      new apiClient.ApiError(409, { detail }),
    );

    renderPage([SQUAT_UPLOAD]);

    await chooseVideo(new File(['abc'], 'clip.mp4', { type: 'video/mp4' }));
    await waitFor(() => expect(screen.getByText('clip.mp4')).toBeDefined());
    fireEvent.click(screen.getByRole('button', { name: 'Upload Video' }));

    expect(await screen.findByText(detail)).toBeDefined();
    // The plan was loaded again: the squat is gone, and the plank is offered instead. The
    // squat's form is gone too, so its video can't be sent again.
    expect(await screen.findByRole('link', { name: /plank/i })).toBeDefined();
    await waitFor(() => expect(api).toHaveBeenCalledTimes(2));
    expect(screen.getByText(detail)).toBeDefined();
    expect(screen.queryByRole('heading', { name: 'Squat' })).toBeNull();
    expect(screen.queryByRole('link', { name: /squat/i })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Upload Video' })).toBeNull();

    // Choosing another exercise starts fresh: no video or message from before.
    fireEvent.click(screen.getByRole('link', { name: /plank/i }));

    expect(await screen.findByRole('heading', { name: 'Plank' })).toBeDefined();
    expect(screen.queryByText(detail)).toBeNull();
    expect(screen.queryByText('clip.mp4')).toBeNull();
  });

  it('says so, and offers the exercises left, when the exercise was removed before the upload (404)', async () => {
    // The therapist took the squat out of the plan after this page loaded, so the API's
    // ownership check refuses the upload.
    const api = fakePlanApi([200, planWith(SQUAT, PLANK)], [200, planWith(PLANK)]);
    vi.mocked(apiClient.uploadWithProgress).mockRejectedValue(
      new apiClient.ApiError(404, { detail: 'Plan exercise not found' }),
    );

    renderPage([SQUAT_UPLOAD]);
    await uploadVideo('clip.mp4');

    expect(await screen.findByText(REMOVED)).toBeDefined();
    // The plan was loaded again, and only the exercises left are offered. The squat's
    // form is gone, so its video can't be sent again.
    await waitFor(() => expect(api).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('link', { name: /plank/i })).toBeDefined();
    expect(screen.queryByRole('link', { name: /squat/i })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Upload Video' })).toBeNull();
  });

  it('keeps a removed exercise out of the plan, even when the plan cannot load again', async () => {
    fakePlanApi([200, planWith(SQUAT, PLANK)], [500, { detail: 'Database unavailable' }]);
    vi.mocked(apiClient.uploadWithProgress).mockRejectedValue(
      new apiClient.ApiError(404, { detail: 'Plan exercise not found' }),
    );

    const { router, queryClient } = renderPage([SQUAT_UPLOAD]);
    await uploadVideo('clip.mp4');

    expect(await screen.findByText(REMOVED)).toBeDefined();
    await waitFor(() =>
      expect(queryClient.getQueryState(getGetMyPlanQueryKey())?.status).toBe('error'),
    );
    // Not offered here, and gone from the cached plan, so My plan doesn't offer it either.
    expect(screen.getByRole('link', { name: /plank/i })).toBeDefined();
    expect(screen.queryByRole('link', { name: /squat/i })).toBeNull();
    const cached = queryClient.getQueryData<PlanResponse>(getGetMyPlanQueryKey());
    expect(cached?.exercises.map((item) => item.id)).toEqual([PLANK.id]);

    // Back at the squat's address after choosing the plank: still no form to send it again.
    fireEvent.click(screen.getByRole('link', { name: /plank/i }));
    expect(await screen.findByRole('heading', { name: 'Plank' })).toBeDefined();
    await goBack(router);
    expect(await screen.findByText(REMOVED)).toBeDefined();
    expect(screen.queryByTestId('file-input')).toBeNull();
  });

  it('treats any other 404 as an ordinary upload error', async () => {
    const api = fakePlanApi([200, planWith(SQUAT, PLANK)]);
    vi.mocked(apiClient.uploadWithProgress).mockRejectedValue(
      new apiClient.ApiError(404, { detail: 'Not Found' }),
    );

    renderPage([SQUAT_UPLOAD]);
    await uploadVideo('clip.mp4');

    expect(await screen.findByText('Not Found')).toBeDefined();
    // Still the squat's form, so the patient can try again, and the plan wasn't reloaded.
    expect(screen.getByRole('heading', { name: 'Squat' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Upload Video' })).toBeDefined();
    expect(api).toHaveBeenCalledTimes(1);
  });

  it('allows cancelling an in-flight upload', async () => {
    let capturedSignal: AbortSignal | undefined;
    vi.mocked(apiClient.uploadWithProgress).mockImplementation((_path, _data, options) => {
      capturedSignal = options?.signal;
      return new Promise((_resolve, reject) => {
        capturedSignal?.addEventListener('abort', () => {
          reject(new DOMException('Upload aborted', 'AbortError'));
        });
      });
    });

    renderPage([SQUAT_UPLOAD]);

    await chooseVideo(new File(['abc'], 'clip.mp4', { type: 'video/mp4' }));
    await waitFor(() => expect(screen.getByText('clip.mp4')).toBeDefined());

    fireEvent.click(screen.getByRole('button', { name: 'Upload Video' }));

    const cancelButton = await screen.findByRole('button', { name: /cancel upload/i });
    fireEvent.click(cancelButton);

    expect(await screen.findByText('Upload was cancelled.')).toBeDefined();
  });

  it("starts over when the address changes to another exercise, even with the browser's Back button", async () => {
    vi.mocked(apiClient.uploadWithProgress).mockResolvedValue({
      id: 'd9b3e1a0-5421-4f1b-85c8-111122223333',
      plan_exercise_id: SQUAT.id,
      status: 'processing',
      created_at: '2026-11-12T12:00:00Z',
    });
    // The patient opened the squat's upload page, then the plank's, and chose a video there.
    const { router } = renderPage([SQUAT_UPLOAD, PLANK_UPLOAD]);
    await chooseVideo(new File(['plank video'], 'plank.mp4', { type: 'video/mp4' }));
    expect(await screen.findByText('plank.mp4')).toBeDefined();

    await goBack(router);

    // The squat's form, without the plank's video.
    expect(await screen.findByRole('heading', { name: 'Squat' })).toBeDefined();
    expect(screen.queryByText('plank.mp4')).toBeNull();
    expect(screen.getByRole('button', { name: 'Upload Video' }).hasAttribute('disabled')).toBe(
      true,
    );

    await uploadVideo('squat.mp4');

    // The squat's id went with the squat's video.
    await waitFor(() => expect(apiClient.uploadWithProgress).toHaveBeenCalledTimes(1));
    const [, sent] = vi.mocked(apiClient.uploadWithProgress).mock.calls[0];
    expect(sent.get('plan_exercise_id')).toBe(SQUAT.id);
    expect((sent.get('video') as File).name).toBe('squat.mp4');
  });

  it("stops the old exercise's upload when the address changes to another exercise", async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(apiClient.uploadWithProgress).mockImplementation((_path, _data, options) => {
      signal = options?.signal;
      return new Promise(() => {}); // still uploading
    });
    const { router } = renderPage([SQUAT_UPLOAD, PLANK_UPLOAD]);
    await uploadVideo('plank.mp4');
    expect(await screen.findByText(/uploading video/i)).toBeDefined();

    await goBack(router);

    expect(await screen.findByRole('heading', { name: 'Squat' })).toBeDefined();
    expect(signal?.aborted).toBe(true);
    expect(screen.queryByText(/uploading video/i)).toBeNull();
  });

  it("drops the old exercise's unfinished length check when the address changes", async () => {
    let finishCheck: (seconds: number) => void = () => {};
    vi.spyOn(videoValidation, 'getVideoDuration').mockImplementation(
      () =>
        new Promise((resolve) => {
          finishCheck = resolve;
        }),
    );
    const { router } = renderPage([SQUAT_UPLOAD, PLANK_UPLOAD]);
    await chooseVideo(new File(['plank video'], 'plank.mp4', { type: 'video/mp4' }));
    expect(await screen.findByText('Checking length...')).toBeDefined();

    await goBack(router);
    expect(await screen.findByRole('heading', { name: 'Squat' })).toBeDefined();
    // The plank video's check ends only now, with a length that is too long.
    await act(async () => finishCheck(125));

    expect(screen.queryByText(/longer than 2 minutes/i)).toBeNull();
    expect(screen.queryByText('Checking length...')).toBeNull();
    expect(screen.queryByText('plank.mp4')).toBeNull();
  });
});
