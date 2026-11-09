import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MantineProvider } from '@mantine/core';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import UploadPage from './UploadPage';
import * as apiClient from '@/apiClient';
import * as videoValidation from '@/utils/videoValidation';

vi.mock('@/apiClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/apiClient')>();
  return {
    ...actual,
    uploadWithProgress: vi.fn(),
  };
});

describe('UploadPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(videoValidation, 'getVideoDuration').mockResolvedValue(15);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  function renderPage(initialEntries = ['/patient/upload']) {
    return render(
      <MantineProvider>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path="/patient/upload" element={<UploadPage />} />
            <Route path="/patient" element={<div>Patient Plan Page</div>} />
          </Routes>
        </MemoryRouter>
      </MantineProvider>,
    );
  }

  it('renders page elements, inputs, and recording tips', () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Upload Video' })).toBeDefined();
    expect(screen.getByLabelText(/plan exercise id/i)).toBeDefined();
    expect(screen.getByRole('button', { name: /record with camera/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /choose video file/i })).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Recording Tips' })).toBeDefined();
  });

  it('configures phone camera capture and desktop file inputs correctly', () => {
    renderPage();

    const cameraInput = screen.getByTestId('camera-input') as HTMLInputElement;
    const fileInput = screen.getByTestId('file-input') as HTMLInputElement;

    expect(cameraInput.type).toBe('file');
    expect(cameraInput.getAttribute('accept')).toBe('video/mp4,video/quicktime,video/webm');
    expect(cameraInput.getAttribute('capture')).toBe('environment');

    expect(fileInput.type).toBe('file');
    expect(fileInput.getAttribute('accept')).toBe('video/mp4,video/quicktime,video/webm');
    expect(fileInput.getAttribute('capture')).toBeNull();
  });

  it('prepopulates Plan Exercise ID from URL search params', () => {
    const testId = '4e8bbd2a-8141-4176-b3aa-5a896d8e27aa';
    renderPage([`/patient/upload?plan_exercise_id=${testId}`]);

    const input = screen.getByLabelText(/plan exercise id/i) as HTMLInputElement;
    expect(input.value).toBe(testId);
  });

  it('rejects submission when Plan Exercise ID is missing', async () => {
    renderPage();

    const fileInput = screen.getByTestId('file-input');
    const validFile = new File(['mock video'], 'exercise.mp4', { type: 'video/mp4' });

    fireEvent.change(fileInput, { target: { files: [validFile] } });

    await waitFor(() => {
      expect(screen.getByText('exercise.mp4')).toBeDefined();
    });

    const uploadButton = screen.getByRole('button', { name: 'Upload Video' });
    fireEvent.click(uploadButton);

    expect(await screen.findByText('Please enter a Plan Exercise ID.')).toBeDefined();
    expect(apiClient.uploadWithProgress).not.toHaveBeenCalled();
  });

  it('validates file size on client-side and prevents upload of empty files', async () => {
    renderPage();

    const fileInput = screen.getByTestId('file-input');
    const emptyFile = new File([], 'empty.mp4', { type: 'video/mp4' });

    fireEvent.change(fileInput, { target: { files: [emptyFile] } });

    expect(await screen.findByText(/couldn't open your video/i)).toBeDefined();
    const uploadButton = screen.getByRole('button', { name: 'Upload Video' });
    expect(uploadButton.hasAttribute('disabled')).toBe(true);
  });

  it('validates file size on client-side and prevents upload of files > 1 GiB', async () => {
    renderPage();

    const fileInput = screen.getByTestId('file-input');
    const largeFile = new File(['content'], 'oversized.mp4', { type: 'video/mp4' });
    Object.defineProperty(largeFile, 'size', {
      value: videoValidation.MAX_VIDEO_UPLOAD_BYTES + 10,
    });

    fireEvent.change(fileInput, { target: { files: [largeFile] } });

    expect(await screen.findByText(/exceeds the 1 GiB limit/i)).toBeDefined();
    const uploadButton = screen.getByRole('button', { name: 'Upload Video' });
    expect(uploadButton.hasAttribute('disabled')).toBe(true);
  });

  it('validates video length on client-side (< 3s)', async () => {
    vi.spyOn(videoValidation, 'getVideoDuration').mockResolvedValue(2.5);
    renderPage();

    const fileInput = screen.getByTestId('file-input');
    const shortFile = new File(['content'], 'short.mp4', { type: 'video/mp4' });

    fireEvent.change(fileInput, { target: { files: [shortFile] } });

    expect(await screen.findByText(/shorter than 3 seconds/i)).toBeDefined();
    const uploadButton = screen.getByRole('button', { name: 'Upload Video' });
    expect(uploadButton.hasAttribute('disabled')).toBe(true);
  });

  it('validates video length on client-side (> 120s)', async () => {
    vi.spyOn(videoValidation, 'getVideoDuration').mockResolvedValue(125);
    renderPage();

    const fileInput = screen.getByTestId('file-input');
    const longFile = new File(['content'], 'long.mp4', { type: 'video/mp4' });

    fireEvent.change(fileInput, { target: { files: [longFile] } });

    expect(await screen.findByText(/longer than 2 minutes/i)).toBeDefined();
    const uploadButton = screen.getByRole('button', { name: 'Upload Video' });
    expect(uploadButton.hasAttribute('disabled')).toBe(true);
  });

  it('successfully uploads valid video, updates progress, and creates a processing session', async () => {
    const sessionResponse = {
      id: 'd9b3e1a0-5421-4f1b-85c8-111122223333',
      plan_exercise_id: '4e8bbd2a-8141-4176-b3aa-5a896d8e27aa',
      status: 'processing' as const,
      created_at: new Date().toISOString(),
    };

    let progressCb: ((ev: apiClient.UploadProgressEvent) => void) | undefined;
    vi.mocked(apiClient.uploadWithProgress).mockImplementation((_path, _data, options) => {
      progressCb = options?.onProgress;
      return new Promise((resolve) => {
        setTimeout(() => {
          progressCb?.({ loaded: 50, total: 100, percent: 50 });
          progressCb?.({ loaded: 100, total: 100, percent: 100 });
          resolve(sessionResponse);
        }, 10);
      });
    });

    renderPage([`/patient/upload?plan_exercise_id=${sessionResponse.plan_exercise_id}`]);

    const fileInput = screen.getByTestId('file-input');
    const validFile = new File(['valid video content'], 'exercise.mp4', { type: 'video/mp4' });

    fireEvent.change(fileInput, { target: { files: [validFile] } });

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

    renderPage(['/patient/upload?plan_exercise_id=4e8bbd2a-8141-4176-b3aa-5a896d8e27aa']);

    const fileInput = screen.getByTestId('file-input');
    const file = new File(['abc'], 'clip.mp4', { type: 'video/mp4' });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => expect(screen.getByText('clip.mp4')).toBeDefined());

    fireEvent.click(screen.getByRole('button', { name: 'Upload Video' }));

    expect(await screen.findByText('Video unreadable')).toBeDefined();
    expect(screen.getByText('Upload failed')).toBeDefined();
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

    renderPage(['/patient/upload?plan_exercise_id=4e8bbd2a-8141-4176-b3aa-5a896d8e27aa']);

    const fileInput = screen.getByTestId('file-input');
    const file = new File(['abc'], 'clip.mp4', { type: 'video/mp4' });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => expect(screen.getByText('clip.mp4')).toBeDefined());

    fireEvent.click(screen.getByRole('button', { name: 'Upload Video' }));

    const cancelButton = await screen.findByRole('button', { name: /cancel upload/i });
    fireEvent.click(cancelButton);

    expect(await screen.findByText('Upload was cancelled.')).toBeDefined();
  });
});
