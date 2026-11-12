import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import UploadPage from './UploadPage';
import * as apiClient from '@/apiClient';
import * as videoValidation from '@/utils/videoValidation';
import { NO_PLAN, PLANK, SQUAT, fakePlanApi, planWith } from './testPlan';

vi.mock('@/apiClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/apiClient')>();
  return {
    ...actual,
    uploadWithProgress: vi.fn(),
  };
});

// The upload page for the squat of the test plan, as its Record / Upload button opens it.
const SQUAT_UPLOAD = `/patient/upload?plan_exercise_id=${SQUAT.id}`;

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

  function renderPage(initialEntries = ['/patient/upload']) {
    // retry: false, so a failed request fails at once instead of being retried.
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <MantineProvider>
          <MemoryRouter initialEntries={initialEntries}>
            <Routes>
              <Route path="/patient/upload" element={<UploadPage />} />
              <Route path="/patient" element={<div>Patient Plan Page</div>} />
            </Routes>
          </MemoryRouter>
        </MantineProvider>
      </QueryClientProvider>,
    );
  }

  /** Picks this video in the file input, once the page shows the form. */
  async function chooseVideo(file: File) {
    const fileInput = await screen.findByTestId('file-input');
    fireEvent.change(fileInput, { target: { files: [file] } });
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
    // The plan was loaded again: the squat is gone, and the plank is offered instead.
    expect(await screen.findByRole('link', { name: /plank/i })).toBeDefined();
    expect(api).toHaveBeenCalledTimes(2);
    expect(screen.getByText(detail)).toBeDefined();
    expect(screen.queryByRole('heading', { name: 'Squat' })).toBeNull();
    expect(screen.queryByRole('link', { name: /squat/i })).toBeNull();

    // Choosing another exercise starts fresh: no video or message from before.
    fireEvent.click(screen.getByRole('link', { name: /plank/i }));

    expect(await screen.findByRole('heading', { name: 'Plank' })).toBeDefined();
    expect(screen.queryByText(detail)).toBeNull();
    expect(screen.queryByText('clip.mp4')).toBeNull();
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
});
