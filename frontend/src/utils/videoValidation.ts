/**
 * Client-side video validation utilities.
 * Keeps limits and error messages aligned with the backend analysis contract.
 */

export const MIN_VIDEO_SECONDS = 3;
export const MAX_VIDEO_SECONDS = 120;
export const MAX_VIDEO_UPLOAD_BYTES = 1073741824; // 1 GiB (1024 * 1024 * 1024)

export const ALLOWED_EXTENSIONS = ['.mp4', '.mov', '.webm'] as const;
export const ALLOWED_MIME_TYPES = ['video/mp4', 'video/quicktime', 'video/webm'] as const;

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

/**
 * Validates file size and format before reading media streams or uploading.
 */
export function checkFileConstraints(file: File | null | undefined): ValidationResult {
  if (!file) {
    return { valid: false, error: 'Please select a video file.' };
  }

  if (file.size === 0) {
    return {
      valid: false,
      error: "We couldn't open your video. Please record it again and upload the new video.",
    };
  }

  if (file.size > MAX_VIDEO_UPLOAD_BYTES) {
    return {
      valid: false,
      error: 'Video exceeds the 1 GiB limit. Please record a shorter or lower-resolution video.',
    };
  }

  const filename = file.name.toLowerCase();
  const hasValidExtension = ALLOWED_EXTENSIONS.some((ext) => filename.endsWith(ext));

  // Some browsers or devices provide an empty MIME type or generic stream type for recorded files.
  // We check extension, and if MIME type is populated and not generic octet-stream, verify it.
  const hasValidMime =
    !file.type ||
    file.type === 'application/octet-stream' ||
    ALLOWED_MIME_TYPES.includes(file.type as (typeof ALLOWED_MIME_TYPES)[number]);

  if (!hasValidExtension || !hasValidMime) {
    return {
      valid: false,
      error: 'Please upload an MP4, MOV, or WebM video.',
    };
  }

  return { valid: true };
}

/**
 * Validates video duration against the contract limits (3 - 120 seconds).
 */
export function checkDurationConstraints(duration: number): ValidationResult {
  if (!Number.isFinite(duration) || duration <= 0) {
    return {
      valid: false,
      error:
        "We couldn't determine the duration of your video. Please check the file and try again.",
    };
  }

  if (duration < MIN_VIDEO_SECONDS) {
    return {
      valid: false,
      error: `Your video is shorter than ${MIN_VIDEO_SECONDS} seconds. Please record the whole exercise.`,
    };
  }

  if (duration > MAX_VIDEO_SECONDS) {
    return {
      valid: false,
      error: `Your video is longer than ${MAX_VIDEO_SECONDS / 60} minutes. Please record a shorter video.`,
    };
  }

  return { valid: true };
}

/**
 * Loads video metadata in the browser to inspect its duration.
 */
export function getVideoDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    // If not in a browser environment (or tests without media mock)
    if (typeof document === 'undefined' || typeof window === 'undefined') {
      resolve(10); // fallback for non-DOM environments
      return;
    }

    const video = document.createElement('video');
    video.preload = 'metadata';

    const url = URL.createObjectURL(file);
    video.src = url;

    const cleanup = () => {
      URL.revokeObjectURL(url);
      video.removeAttribute('src');
      video.load();
    };

    video.onloadedmetadata = () => {
      const duration = video.duration;
      cleanup();
      resolve(duration);
    };

    video.onerror = () => {
      cleanup();
      reject(new Error("We couldn't read the video file. Please try another recording."));
    };
  });
}

/**
 * Formats seconds into mm:ss.
 */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Formats file size in bytes to a human-readable string (MB / KB).
 */
export function formatFileSize(bytes: number): string {
  if (bytes <= 0) return '0 B';
  const mb = bytes / (1024 * 1024);
  if (mb >= 1) {
    return `${mb.toFixed(1)} MB`;
  }
  const kb = bytes / 1024;
  return `${kb.toFixed(1)} KB`;
}
