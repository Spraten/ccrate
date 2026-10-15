/** @returns {{ status: "idle", error: string } | null} */
export function recoverFeedbackSubmissionError(result, status) {
  if (status !== 413) return null;
  return { status: "idle", error: result?.error || "The report is too large to send." };
}

export function feedbackStatusFromResult(result) {
  return ["pending", "rejected", "submitted"].includes(result?.status) ? result.status : "idle";
}

export function feedbackCanSubmit(status, description) {
  const text = typeof description === "string" ? description.trim() : "";
  return text.length >= 10 && !["sending", "pending", "submitted"].includes(status);
}

export function feedbackRequestIdForSubmit(status, requestId) {
  return status === "rejected" ? "" : requestId;
}
