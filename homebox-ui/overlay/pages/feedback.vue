<script setup lang="ts">
  import BaseCard from "@/components/Base/Card.vue";
  import { Button } from "@/components/ui/button";
  import { Textarea } from "@/components/ui/textarea";

  definePageMeta({ middleware: ["auth"] });
  useHead({ title: "Report feedback · C-Crate" });

  type ReportDraft = { requestId: string; type: string; description: string };
  const auth = useAuthContext();
  const reportType = ref("bug"), description = ref(""), requestId = ref("");
  const status = ref<"idle" | "sending" | "pending" | "submitted" | "rejected">("idle");
  const issueUrl = ref(""), error = ref(""), checking = ref(false);
  let loadingDraft = false;
  const draftKey = computed(() => auth.user?.id ? `ccrate-feedback-draft:${auth.user.id}` : "");
  const canSubmit = computed(() => !!description.value.trim() && description.value.trim().length >= 10 && !["sending", "pending", "submitted"].includes(status.value));

  function saveDraft() {
    if (!import.meta.client || !draftKey.value || loadingDraft) return;
    localStorage.setItem(draftKey.value, JSON.stringify({ requestId: requestId.value, type: reportType.value, description: description.value }));
  }

  function loadDraft() {
    if (!import.meta.client) return;
    loadingDraft = true;
    requestId.value = ""; reportType.value = "bug"; description.value = "";
    status.value = "idle"; issueUrl.value = ""; error.value = "";
    if (!draftKey.value) { loadingDraft = false; return; }
    try {
      const draft = JSON.parse(localStorage.getItem(draftKey.value) || "null") as ReportDraft | null;
      if (draft && typeof draft === "object") {
        requestId.value = typeof draft.requestId === "string" ? draft.requestId : "";
        reportType.value = typeof draft.type === "string" ? draft.type : "bug";
        description.value = typeof draft.description === "string" ? draft.description : "";
        if (requestId.value) status.value = "pending";
      }
    } catch { localStorage.removeItem(draftKey.value); }
    finally { loadingDraft = false; }
  }

  function newRequestId() {
    if (crypto.randomUUID) return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6]! & 15) | 64; bytes[8] = (bytes[8]! & 63) | 128;
    const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  function startAnotherReport() {
    requestId.value = ""; reportType.value = "bug"; description.value = "";
    status.value = "idle"; issueUrl.value = ""; error.value = "";
  }

  async function parseResponse(response: Response) {
    const result = await response.json().catch(() => ({}));
    if (!response.ok && response.status !== 202) throw Object.assign(new Error(result.error || "C-Crate could not confirm the report."), { result, status: response.status });
    return result;
  }

  function applyResult(result: { status?: string; request_id?: string; issue_url?: string; error?: string }) {
    if (result.request_id) requestId.value = result.request_id;
    if (result.status === "submitted") {
      status.value = "submitted";
      issueUrl.value = result.issue_url || "";
      error.value = "";
      if (draftKey.value) localStorage.removeItem(draftKey.value);
      return;
    }
    if (result.status === "rejected") status.value = "rejected";
    else if (result.status === "pending") status.value = "pending";
    else status.value = "idle";
    error.value = result.error || (status.value === "pending" ? "The result is not confirmed yet. Check status again; the report will not be sent a second time." : "");
  }

  async function submit() {
    if (!canSubmit.value) return;
    error.value = "";
    if (status.value === "rejected") requestId.value = "";
    if (!requestId.value) requestId.value = newRequestId();
    status.value = "sending";
    saveDraft();
    try {
      const response = await fetch("/ccrate-api/feedback", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Idempotency-Key": requestId.value },
        body: JSON.stringify({ type: reportType.value, description: description.value }),
      });
      applyResult(await parseResponse(response));
    } catch (cause) {
      const result = (cause as { result?: { status?: string; error?: string } }).result;
      if (result) applyResult(result);
      else {
        status.value = "pending";
        error.value = "C-Crate did not receive a confirmation. Check report status before trying again.";
      }
      saveDraft();
    }
  }

  async function checkStatus() {
    if (!requestId.value || checking.value) return;
    checking.value = true; error.value = "";
    try {
      const response = await fetch(`/ccrate-api/feedback/${encodeURIComponent(requestId.value)}`, { credentials: "same-origin" });
      if (response.status === 404) {
        status.value = "idle";
        error.value = "No report was recorded for this request. Your saved draft is ready to submit.";
        return;
      }
      applyResult(await parseResponse(response));
      saveDraft();
    } catch (cause) {
      error.value = (cause as Error).message || "C-Crate could not check the report status.";
    } finally { checking.value = false; }
  }

  watch(draftKey, loadDraft, { immediate: true, flush: "sync" });
  watch([reportType, description], saveDraft);
</script>

<template>
  <main class="mx-auto w-full max-w-3xl space-y-5 p-4 sm:p-6">
    <header class="space-y-2">
      <p class="text-sm font-medium text-primary">C-Crate feedback</p>
      <h1 class="text-3xl font-semibold tracking-tight">Report a problem or idea</h1>
      <p class="max-w-2xl text-muted-foreground">Tell us what happened or what would make your inventory work better. Reports are sent to the C-Crate project maintainers.</p>
      <p class="max-w-2xl text-sm text-muted-foreground">Reports are posted to the C-Crate GitHub repository. Do not include passwords, badge keys, or other sensitive information.</p>
    </header>

    <BaseCard>
      <template #title>Your report</template>
      <form class="space-y-5 p-4 sm:p-6" @submit.prevent="submit">
        <label class="block space-y-2" for="feedback-type">
          <span class="text-sm font-medium">Type</span>
          <select id="feedback-type" v-model="reportType" :disabled="status === 'pending' || status === 'sending' || status === 'submitted'" class="h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
            <option value="bug">Something is broken</option>
            <option value="idea">Feature idea</option>
            <option value="question">Question</option>
            <option value="other">Other feedback</option>
          </select>
        </label>
        <label class="block space-y-2" for="feedback-description">
          <span class="text-sm font-medium">Description</span>
          <Textarea id="feedback-description" v-model="description" :disabled="status === 'pending' || status === 'sending' || status === 'submitted'" rows="7" maxlength="5000" required minlength="10" placeholder="What were you doing, what happened, and what did you expect?" />
          <span class="text-xs text-muted-foreground">{{ description.length }} / 5000 characters</span>
        </label>
        <p v-if="error" class="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm" role="alert">{{ error }}</p>
        <p v-if="status === 'pending'" class="text-sm text-muted-foreground" role="status">The request is saved. Check its status before taking another action.</p>
        <p v-if="status === 'submitted'" class="text-sm text-green-700" role="status">
          Report submitted.
          <a v-if="issueUrl" class="underline underline-offset-2" :href="issueUrl" target="_blank" rel="noreferrer">View the GitHub issue</a>
        </p>
        <div class="flex flex-wrap gap-3">
          <Button type="submit" :disabled="!canSubmit">{{ status === 'rejected' ? 'Edit and submit again' : 'Submit report' }}</Button>
          <Button v-if="status === 'submitted'" type="button" variant="outline" @click="startAnotherReport">Start another report</Button>
          <Button v-if="requestId && status !== 'submitted'" type="button" variant="outline" :disabled="checking || status === 'sending'" @click="checkStatus">{{ checking ? 'Checking…' : 'Check report status' }}</Button>
        </div>
      </form>
    </BaseCard>
  </main>
</template>
