// TEMPORARY: delete once an API route returns the result (SCRUM-64)
// and the Orval hooks are regenerated. Shape comes from docs/analysis-result.md.

export type ResultStatus = "complete" | "failed";
export type Side = "left" | "right" | "both" | null;

export interface RepIssue {
  code: string; // open string, e.g. "knees_cave_in"
  message: string; // plain language, shown as-is
}

export interface Rep {
  index: number; // 1, 2, 3...
  start_seconds: number;
  end_seconds: number;
  side: Side;
  score: number; // 0 to 100
  issues: RepIssue[];
  metrics: Record<string, number>;
}

export interface AnalysisResult {
  status: ResultStatus;
  rep_count: number | null;
  hold_seconds: number | null; // can be 0
  form_score: number | null; // 0 to 100, null when reps is empty
  reps: Rep[]; // for a plank, each entry is one unbroken hold
  feedback: string[]; // up to 3 tips
  error_code: string | null;
  error_message: string | null;
  analyzer_version: string | null;
}