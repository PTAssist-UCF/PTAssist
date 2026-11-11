import { describe, expect, it } from 'vitest';
import {
  checkDurationConstraints,
  checkFileConstraints,
  formatDuration,
  formatFileSize,
  MAX_VIDEO_SECONDS,
  MAX_VIDEO_UPLOAD_BYTES,
  MIN_VIDEO_SECONDS,
} from './videoValidation';

describe('videoValidation', () => {
  describe('checkFileConstraints', () => {
    it('rejects null or missing file', () => {
      expect(checkFileConstraints(null).valid).toBe(false);
      expect(checkFileConstraints(undefined).valid).toBe(false);
      expect(checkFileConstraints(null).error).toContain('Please select a video file');
    });

    it('rejects empty (0 byte) file', () => {
      const emptyFile = new File([], 'empty.mp4', { type: 'video/mp4' });
      const result = checkFileConstraints(emptyFile);
      expect(result.valid).toBe(false);
      expect(result.error).toContain("couldn't open your video");
    });

    it('rejects file larger than 1 GiB', () => {
      const largeFile = new File(['x'], 'large.mp4', { type: 'video/mp4' });
      Object.defineProperty(largeFile, 'size', { value: MAX_VIDEO_UPLOAD_BYTES + 1 });
      const result = checkFileConstraints(largeFile);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('1 GiB limit');
    });

    it('accepts file equal to 1 GiB', () => {
      const validFile = new File(['x'], 'exact.mp4', { type: 'video/mp4' });
      Object.defineProperty(validFile, 'size', { value: MAX_VIDEO_UPLOAD_BYTES });
      expect(checkFileConstraints(validFile).valid).toBe(true);
    });

    it('rejects files with unsupported extensions', () => {
      const txtFile = new File(['content'], 'exercise.txt', { type: 'text/plain' });
      const result = checkFileConstraints(txtFile);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('MP4, MOV, or WebM');
    });

    it('accepts valid .mp4, .mov, and .webm files', () => {
      const mp4 = new File(['content'], 'exercise.mp4', { type: 'video/mp4' });
      const mov = new File(['content'], 'exercise.mov', { type: 'video/quicktime' });
      const webm = new File(['content'], 'exercise.webm', { type: 'video/webm' });

      expect(checkFileConstraints(mp4).valid).toBe(true);
      expect(checkFileConstraints(mov).valid).toBe(true);
      expect(checkFileConstraints(webm).valid).toBe(true);
    });

    it('accepts valid video file with octet-stream mime or empty mime (common on mobile)', () => {
      const mobileClip = new File(['content'], 'recording.mp4', {
        type: 'application/octet-stream',
      });
      const noMimeClip = new File(['content'], 'recording.mov', { type: '' });

      expect(checkFileConstraints(mobileClip).valid).toBe(true);
      expect(checkFileConstraints(noMimeClip).valid).toBe(true);
    });
  });

  describe('checkDurationConstraints', () => {
    it('rejects non-finite or non-positive durations', () => {
      expect(checkDurationConstraints(NaN).valid).toBe(false);
      expect(checkDurationConstraints(0).valid).toBe(false);
      expect(checkDurationConstraints(-5).valid).toBe(false);
      expect(checkDurationConstraints(Infinity).valid).toBe(false);
    });

    it('rejects video shorter than MIN_VIDEO_SECONDS (3s)', () => {
      const result = checkDurationConstraints(MIN_VIDEO_SECONDS - 0.1);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('shorter than 3 seconds');
    });

    it('rejects video longer than MAX_VIDEO_SECONDS (120s)', () => {
      const result = checkDurationConstraints(MAX_VIDEO_SECONDS + 0.1);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('longer than 2 minutes');
    });

    it('accepts videos within the 3s to 120s range', () => {
      expect(checkDurationConstraints(MIN_VIDEO_SECONDS).valid).toBe(true);
      expect(checkDurationConstraints(45.5).valid).toBe(true);
      expect(checkDurationConstraints(MAX_VIDEO_SECONDS).valid).toBe(true);
    });
  });

  describe('formatting helpers', () => {
    it('formats duration in mm:ss', () => {
      expect(formatDuration(0)).toBe('0:00');
      expect(formatDuration(5)).toBe('0:05');
      expect(formatDuration(65)).toBe('1:05');
      expect(formatDuration(120)).toBe('2:00');
    });

    it('formats file sizes in MB and KB', () => {
      expect(formatFileSize(0)).toBe('0 B');
      expect(formatFileSize(500 * 1024)).toBe('500.0 KB');
      expect(formatFileSize(15.4 * 1024 * 1024)).toBe('15.4 MB');
    });
  });
});
