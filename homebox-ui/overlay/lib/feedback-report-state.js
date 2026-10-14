export function recoverFeedbackSubmissionError(result, status) {
  if (status !== 413) return null;
  return { status: "idle", error: result?.error || "The report is too large to send." };
}
