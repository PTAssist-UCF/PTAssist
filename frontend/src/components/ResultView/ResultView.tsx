import { Alert, Badge, Button, Card, Group, List, Stack, Text } from "@mantine/core";
import type { AnalysisResult, Side } from "./types";
import { BAND_COLOR, BAND_LABEL, getScoreBand } from "./scoreBand";

interface ResultViewProps {
  result: AnalysisResult;
  // Called when the user clicks "Upload again". The parent decides what that does.
  onReupload?: () => void;
}

const SIDE_LABEL: Record<Exclude<Side, null>, string> = {
  left: "Left",
  right: "Right",
  both: "Both sides",
};

function ScoreBadge({ score, testId }: { score: number; testId?: string }) {
  const band = getScoreBand(score);
  return (
    <Badge color={BAND_COLOR[band]} data-testid={testId} data-band={band}>
      {score} · {BAND_LABEL[band]}
    </Badge>
  );
}

export function ResultView({ result, onReupload }: ResultViewProps) {
  // 1. Failed state
  if (result.status === "failed") {
    const canReupload = result.error_code !== "unknown_exercise" && onReupload;
    return (
      <Alert color="red" title="We couldn't analyze your video" data-testid="result-failed">
        <Stack gap="sm">
          <Text>{result.error_message ?? "Something went wrong. Please try again."}</Text>
          {canReupload && <Button onClick={onReupload}>Upload again</Button>}
        </Stack>
      </Alert>
    );
  }

  // 2. Hold time wins when it's not null (0 is a real value)
  const isHold = result.hold_seconds !== null;
  const mainValue = isHold ? result.hold_seconds!.toFixed(1) : String(result.rep_count ?? 0);
  const mainLabel = isHold ? "seconds held" : "reps";
  const entryLabel = isHold ? "Hold" : "Rep";

  return (
    <Card withBorder padding="lg">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text size="2rem" fw={700} data-testid="main-value">
              {mainValue}
            </Text>
            <Text c="dimmed">{mainLabel}</Text>
          </div>
          {result.form_score !== null && (
            <ScoreBadge score={result.form_score} testId="form-score" />
          )}
        </Group>

        {result.feedback.length > 0 && (
          <div>
            <Text fw={600}>Feedback</Text>
            <List>
              {result.feedback.map((tip) => (
                <List.Item key={tip}>{tip}</List.Item>
              ))}
            </List>
          </div>
        )}

        {result.reps.length > 0 && (
          <Stack gap="xs">
            <Text fw={600}>{isHold ? "Holds" : "Reps"}</Text>
            {result.reps.map((rep) => (
              <Card key={rep.index} withBorder padding="sm" data-testid={`rep-${rep.index}`}>
                <Group justify="space-between">
                  <Text>
                    {entryLabel} {rep.index}
                    {rep.side ? ` · ${SIDE_LABEL[rep.side]}` : ""}
                    <Text span c="dimmed">
                      {" "}
                      ({rep.start_seconds.toFixed(1)}s to {rep.end_seconds.toFixed(1)}s)
                    </Text>
                  </Text>
                  <ScoreBadge score={rep.score} testId={`rep-${rep.index}-score`} />
                </Group>
                {rep.issues.length > 0 && (
                  <List size="sm" mt="xs">
                    {rep.issues.map((issue) => (
                      <List.Item key={issue.code}>{issue.message}</List.Item>
                    ))}
                  </List>
                )}
              </Card>
            ))}
          </Stack>
        )}
      </Stack>
    </Card>
  );
}