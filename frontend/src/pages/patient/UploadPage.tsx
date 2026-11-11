import { useState, useRef, useEffect, type ChangeEvent, type DragEvent } from 'react';
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom';
import {
  Container,
  Title,
  Text,
  Paper,
  TextInput,
  Button,
  Group,
  Stack,
  Alert,
  Progress,
  Badge,
  Card,
  Box,
  SimpleGrid,
  List,
  ThemeIcon,
} from '@mantine/core';

import { uploadWithProgress, ApiError } from '@/apiClient';
import type { SessionResponse } from '@/api/model';
import {
  checkFileConstraints,
  checkDurationConstraints,
  getVideoDuration,
  formatDuration,
  formatFileSize,
  MIN_VIDEO_SECONDS,
  MAX_VIDEO_SECONDS,
} from '@/utils/videoValidation';

export default function UploadPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const location = useLocation();

  // Prepopulate plan_exercise_id from search params (?plan_exercise_id=...) or router state
  const initialPlanExerciseId =
    searchParams.get('plan_exercise_id') ||
    searchParams.get('exerciseId') ||
    (location.state as { planExerciseId?: string } | null)?.planExerciseId ||
    '';

  const [planExerciseId, setPlanExerciseId] = useState(initialPlanExerciseId);
  const [planExerciseError, setPlanExerciseError] = useState<string | null>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [videoDuration, setVideoDuration] = useState<number | null>(null);
  const [isCheckingDuration, setIsCheckingDuration] = useState(false);

  const [validationError, setValidationError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [createdSession, setCreatedSession] = useState<SessionResponse | null>(null);

  const [isDragOver, setIsDragOver] = useState(false);

  const cameraInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  // Keep previewUrlRef in sync and revoke on unmount
  useEffect(() => {
    previewUrlRef.current = previewUrl;
  }, [previewUrl]);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const processFile = async (file: File) => {
    setValidationError(null);
    setUploadError(null);
    setSelectedFile(file);
    setVideoDuration(null);

    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
    }
    const newPreviewUrl = URL.createObjectURL(file);
    setPreviewUrl(newPreviewUrl);

    // 1. Client-side file format & size checks
    const fileCheck = checkFileConstraints(file);
    if (!fileCheck.valid) {
      setValidationError(fileCheck.error || 'Invalid video file.');
      return;
    }

    // 2. Client-side video length check
    setIsCheckingDuration(true);
    try {
      const duration = await getVideoDuration(file);
      setVideoDuration(duration);

      const durationCheck = checkDurationConstraints(duration);
      if (!durationCheck.valid) {
        setValidationError(durationCheck.error || 'Invalid video length.');
      }
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "We couldn't read the video file. Please try another recording.";
      setValidationError(message);
    } finally {
      setIsCheckingDuration(false);
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      void processFile(file);
    }
    // Reset inputs so picking the same file again triggers change
    e.target.value = '';
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      void processFile(file);
    }
  };

  const handleClearFile = () => {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
    }
    setPreviewUrl(null);
    setSelectedFile(null);
    setVideoDuration(null);
    setValidationError(null);
    setUploadError(null);
  };

  const handleCancelUpload = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsUploading(false);
    setUploadProgress(0);
  };

  const handleSubmit = async () => {
    setUploadError(null);

    if (!planExerciseId.trim()) {
      setPlanExerciseError('Please enter a Plan Exercise ID.');
      return;
    }
    setPlanExerciseError(null);

    if (!selectedFile) {
      setValidationError('Please select or record a video first.');
      return;
    }

    if (validationError) {
      return;
    }

    const formData = new FormData();
    formData.append('plan_exercise_id', planExerciseId.trim());
    formData.append('video', selectedFile);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    setIsUploading(true);
    setUploadProgress(0);

    try {
      const session = await uploadWithProgress<SessionResponse>('/sessions', formData, {
        signal: abortController.signal,
        onProgress: (event) => {
          setUploadProgress(event.percent);
        },
      });

      setCreatedSession(session);
      setIsUploading(false);

      // Automatically navigate back to /patient after successful upload
      setTimeout(() => {
        navigate('/patient', {
          state: {
            uploadedSessionId: session.id,
            status: session.status,
          },
        });
      }, 1500);
    } catch (err) {
      setIsUploading(false);
      if (err instanceof DOMException && err.name === 'AbortError') {
        setUploadError('Upload was cancelled.');
        return;
      }
      if (err instanceof ApiError) {
        const detail = (err.body as { detail?: string } | undefined)?.detail;
        setUploadError(
          typeof detail === 'string'
            ? detail
            : `Upload failed with status ${err.status}. Please try again.`,
        );
      } else {
        setUploadError(
          err instanceof Error
            ? err.message
            : 'Could not upload video. Please check your connection and try again.',
        );
      }
    }
  };

  return (
    <Container size="md" py="lg">
      <Stack gap="lg">
        <div>
          <Title order={1} size="h2" mb="xs">
            Upload Video
          </Title>
          <Text c="dimmed">
            Record or choose a video of your exercise session for AI-augmented form analysis.
          </Text>
        </div>

        {createdSession && (
          <Alert color="teal" title="Upload complete!">
            <Stack gap="xs">
              <Group gap="xs">
                <Text size="sm">
                  Session{' '}
                  <Text span fw={600}>
                    {createdSession.id}
                  </Text>{' '}
                  was successfully created and is now
                </Text>
                <Badge color="yellow" variant="light">
                  processing
                </Badge>
              </Group>
              <Text size="xs" c="dimmed">
                Redirecting back to your plan...
              </Text>
            </Stack>
          </Alert>
        )}

        <Paper withBorder p="lg" radius="md">
          <Stack gap="md">
            <TextInput
              label="Plan Exercise ID"
              placeholder="e.g. 123e4567-e89b-12d3-a456-426614174000"
              description="The identifier of your assigned exercise. Auto-filled when starting from My Plan."
              value={planExerciseId}
              onChange={(e) => {
                setPlanExerciseId(e.currentTarget.value);
                if (planExerciseError) setPlanExerciseError(null);
              }}
              error={planExerciseError}
              disabled={isUploading || !!createdSession}
              required
            />

            {/* Hidden file inputs for Camera recording & File picking */}
            <input
              type="file"
              ref={cameraInputRef}
              accept="video/mp4,video/quicktime,video/webm"
              capture="environment"
              style={{ display: 'none' }}
              onChange={handleFileChange}
              data-testid="camera-input"
            />
            <input
              type="file"
              ref={fileInputRef}
              accept="video/mp4,video/quicktime,video/webm"
              style={{ display: 'none' }}
              onChange={handleFileChange}
              data-testid="file-input"
            />

            {!selectedFile ? (
              <Box>
                <Text size="sm" fw={500} mb="xs">
                  Exercise Recording
                </Text>
                <Paper
                  withBorder
                  p="xl"
                  radius="md"
                  style={{
                    borderStyle: 'dashed',
                    backgroundColor: isDragOver ? 'var(--mantine-color-teal-0)' : undefined,
                    borderColor: isDragOver ? 'var(--mantine-color-teal-5)' : undefined,
                    textAlign: 'center',
                  }}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                >
                  <Stack align="center" gap="md">
                    <Text size="sm" c="dimmed">
                      Record a new video using your camera, pick a recorded clip from your phone, or
                      drag and drop a file here.
                    </Text>

                    <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" w="100%" maw={400}>
                      <Button
                        color="teal"
                        size="md"
                        radius="md"
                        onClick={() => cameraInputRef.current?.click()}
                        disabled={isUploading || !!createdSession}
                      >
                        Record with Camera
                      </Button>
                      <Button
                        variant="default"
                        size="md"
                        radius="md"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={isUploading || !!createdSession}
                      >
                        Choose Video File
                      </Button>
                    </SimpleGrid>

                    <Text size="xs" c="dimmed">
                      Accepted formats: MP4, MOV, WebM • Length: {MIN_VIDEO_SECONDS}s to{' '}
                      {MAX_VIDEO_SECONDS / 60}m • Max size: 1 GiB
                    </Text>
                  </Stack>
                </Paper>
              </Box>
            ) : (
              <Card withBorder radius="md" p="md">
                <Stack gap="sm">
                  <Group justify="space-between" align="center">
                    <div>
                      <Text fw={600} size="sm">
                        {selectedFile.name}
                      </Text>
                      <Group gap="xs" mt={4}>
                        <Badge size="sm" variant="light" color="gray">
                          {formatFileSize(selectedFile.size)}
                        </Badge>
                        {isCheckingDuration ? (
                          <Badge size="sm" variant="outline" color="blue">
                            Checking length...
                          </Badge>
                        ) : videoDuration !== null ? (
                          <Badge
                            size="sm"
                            variant="light"
                            color={
                              videoDuration < MIN_VIDEO_SECONDS || videoDuration > MAX_VIDEO_SECONDS
                                ? 'red'
                                : 'teal'
                            }
                          >
                            Duration: {formatDuration(videoDuration)}
                          </Badge>
                        ) : null}
                      </Group>
                    </div>

                    {!isUploading && !createdSession && (
                      <Button variant="subtle" color="red" size="xs" onClick={handleClearFile}>
                        Change video
                      </Button>
                    )}
                  </Group>

                  {previewUrl && (
                    <Box mt="xs">
                      <video
                        src={previewUrl}
                        controls
                        style={{
                          width: '100%',
                          maxHeight: '300px',
                          borderRadius: '8px',
                          backgroundColor: '#000',
                        }}
                      />
                    </Box>
                  )}
                </Stack>
              </Card>
            )}

            {validationError && (
              <Alert color="red" title="Cannot upload video">
                {validationError}
              </Alert>
            )}

            {uploadError && (
              <Alert color="red" title="Upload failed">
                {uploadError}
              </Alert>
            )}

            {isUploading && (
              <Card withBorder radius="md" p="md" bg="gray.0">
                <Stack gap="xs">
                  <Group justify="space-between">
                    <Text size="sm" fw={500}>
                      Uploading video...
                    </Text>
                    <Text size="sm" fw={600}>
                      {uploadProgress}%
                    </Text>
                  </Group>
                  <Progress value={uploadProgress} animated size="lg" radius="xl" color="teal" />
                  <Group justify="flex-end" mt="xs">
                    <Button variant="default" size="xs" color="red" onClick={handleCancelUpload}>
                      Cancel Upload
                    </Button>
                  </Group>
                </Stack>
              </Card>
            )}

            <Group justify="flex-end" mt="sm">
              <Button variant="default" disabled={isUploading} onClick={() => navigate('/patient')}>
                Back to Plan
              </Button>
              <Button
                color="teal"
                disabled={
                  !selectedFile ||
                  isCheckingDuration ||
                  !!validationError ||
                  isUploading ||
                  !!createdSession
                }
                loading={isUploading}
                onClick={handleSubmit}
              >
                Upload Video
              </Button>
            </Group>
          </Stack>
        </Paper>

        <Paper withBorder p="md" radius="md">
          <Title order={3} size="h4" mb="sm">
            Recording Tips
          </Title>
          <List spacing="xs" size="sm" c="dimmed">
            <List.Item
              icon={
                <ThemeIcon color="teal" size={20} radius="xl">
                  •
                </ThemeIcon>
              }
            >
              <Text span fw={500} c="dark">
                Position your camera:
              </Text>{' '}
              Place your phone or camera at waist or chest height, propped up securely.
            </List.Item>
            <List.Item
              icon={
                <ThemeIcon color="teal" size={20} radius="xl">
                  •
                </ThemeIcon>
              }
            >
              <Text span fw={500} c="dark">
                Full body in frame:
              </Text>{' '}
              Step back so your entire body from head to toes is clearly visible throughout the
              movement.
            </List.Item>
            <List.Item
              icon={
                <ThemeIcon color="teal" size={20} radius="xl">
                  •
                </ThemeIcon>
              }
            >
              <Text span fw={500} c="dark">
                Good lighting & solo framing:
              </Text>{' '}
              Ensure you are well lit from the front, and make sure no other people are in the
              frame.
            </List.Item>
            <List.Item
              icon={
                <ThemeIcon color="teal" size={20} radius="xl">
                  •
                </ThemeIcon>
              }
            >
              <Text span fw={500} c="dark">
                Timing:
              </Text>{' '}
              Perform your reps at a steady, controlled pace. Videos must be between{' '}
              {MIN_VIDEO_SECONDS} seconds and {MAX_VIDEO_SECONDS / 60} minutes.
            </List.Item>
          </List>
        </Paper>
      </Stack>
    </Container>
  );
}
