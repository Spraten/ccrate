import unittest
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


class FeedbackUiContractTests(unittest.TestCase):
    def test_tweak_category_uses_the_existing_type_payload_field(self):
        page = (ROOT / "homebox-ui/overlay/pages/feedback.vue").read_text()
        self.assertIn('<option value="tweak">Tweak / improvement</option>', page)
        self.assertIn('body: JSON.stringify({ type: reportType.value, description: description.value })', page)

    def test_recovered_feedback_status_keeps_idle_as_a_literal_type(self):
        helper = (ROOT / "homebox-ui/overlay/lib/feedback-report-state.js").read_text()
        self.assertIn('@returns {{ status: "idle", error: string } | null}', helper)

    def test_report_is_linked_from_the_collapsed_more_navigation(self):
        builder = (ROOT / "deploy/build-homebox-ui.py").read_text()
        self.assertIn('{ id: 92, name: computed(() => "Report feedback"), to: "/feedback"', builder)

    def test_submission_status_uses_a_theme_aware_success_color(self):
        page = (ROOT / "homebox-ui/overlay/pages/feedback.vue").read_text()
        submitted = page[page.index("<p v-if=\"status === 'submitted'\""):page.index("Report submitted.")]
        self.assertIn("ccrate-feedback-submitted", submitted)
        self.assertNotIn("dark:text-green-300", submitted)
        styles = (ROOT / "homebox-ui/overlay/assets/css/ccrate.css").read_text()
        self.assertIn(":root.theme-night #app .ccrate-feedback-submitted", styles)

    def test_page_keeps_request_identity_per_native_user_and_never_contains_a_github_token(self):
        page = (ROOT / "homebox-ui/overlay/pages/feedback.vue").read_text()
        self.assertIn('definePageMeta({ middleware: ["auth"] })', page)
        self.assertIn('`ccrate-feedback-draft:${auth.user.id}`', page)
        self.assertIn('"Idempotency-Key": capture.requestId', page)
        self.assertIn('"X-Crate-Actor-ID": capture.actorId', page)
        self.assertIn('feedbackActionIsCurrent(capture, currentAction())', page)
        self.assertIn('fetch("/api/v1/users/self"', page)
        self.assertIn('if (!saveDraft(capture.draftKey', page)
        self.assertIn('status.value = "idle";', page)
        self.assertLess(page.index('if (!saveDraft(capture.draftKey'), page.index('fetch("/ccrate-api/feedback"'))
        self.assertIn('watch([reportType, description], () => saveDraft());', page)
        self.assertIn('persistCurrentStatus(capture.draftKey);', page)
        self.assertIn('persistFeedbackStatus(localStorage, key,', page)
        self.assertIn('if (actionIsCurrent(capture)) persistCurrentStatus(capture.draftKey);', page)
        self.assertNotIn('if (actionIsCurrent(capture)) saveDraft(capture.draftKey);', page)
        self.assertIn('"/ccrate-api/feedback"', page)
        self.assertNotIn("CCRATE_GITHUB_TOKEN", page)

    def test_draft_watch_ignores_vue_new_and_old_value_arguments(self):
        page = (ROOT / "homebox-ui/overlay/pages/feedback.vue").resolve().as_uri()
        script = f'''import {{ readFileSync }} from "node:fs";
const page = readFileSync(new URL("{page}"), "utf8");
const callbackSource = page.match(/watch\\(\\[reportType, description\\],\\s*(.*?)\\);/s)?.[1];
if (!callbackSource) process.exit(1);
let args;
const callback = new Function("saveDraft", `return ${{callbackSource}};`)((...values) => args = values);
callback(["idea", "new"], ["bug", "old"]);
if (args.length !== 0) process.exit(2);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_confirmed_report_is_removed_instead_of_recreated_as_pending(self):
        helper = (ROOT / "homebox-ui/overlay/lib/feedback-report-identity.js").resolve().as_uri()
        script = f'''import {{ persistFeedbackStatus }} from "{helper}";
const entries = new Map([["draft-a", JSON.stringify({{requestId:"req-a", description:"sent"}})]]);
const storage = {{setItem(key, value) {{entries.set(key, value);}}, removeItem(key) {{entries.delete(key);}}}};
const saved = persistFeedbackStatus(storage, "draft-a", {{requestId:"req-a", description:"sent"}}, "submitted");
if (!saved || entries.has("draft-a")) process.exit(1);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_409_confirmed_submission_path_keeps_the_draft_cleared(self):
        page = (ROOT / "homebox-ui/overlay/pages/feedback.vue").read_text()
        catch_block = page[page.index("    } catch (cause) {", page.index("async function submit")):page.index("  async function checkStatus")]
        self.assertIn('const result = (cause as { result?', catch_block)
        self.assertIn('const recovered = recoverFeedbackSubmissionError(result,', catch_block)
        self.assertIn('} else applyResult(result, capture);', catch_block)
        self.assertIn('persistCurrentStatus(capture.draftKey);', catch_block)
        self.assertIn('if (actionIsCurrent(capture)) persistCurrentStatus(capture.draftKey);', catch_block)
        self.assertNotIn('if (actionIsCurrent(capture)) saveDraft(capture.draftKey);', catch_block)

        helper = (ROOT / "homebox-ui/overlay/lib/feedback-report-identity.js").resolve().as_uri()
        script = f'''import {{ persistFeedbackStatus }} from "{helper}";
const entries = new Map([["draft-a", JSON.stringify({{requestId:"req-a"}})]]);
const storage = {{setItem(key, value) {{entries.set(key, value);}}, removeItem(key) {{entries.delete(key);}}}};
const statusFrom409 = "submitted";
persistFeedbackStatus(storage, "draft-a", {{requestId:"req-a"}}, statusFrom409);
persistFeedbackStatus(storage, "draft-a", {{requestId:"req-a"}}, statusFrom409);
if (entries.has("draft-a")) process.exit(1);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_413_response_is_handled_as_a_report_error_before_actor_comparison(self):
        page = (ROOT / "homebox-ui/overlay/pages/feedback.vue").read_text()
        parse_response = page[page.index("async function parseResponse"):page.index("async function verifyCurrentActor")]
        self.assertLess(parse_response.index('response.status === 413'), parse_response.index('result.actor_id'))
        self.assertIn('status: response.status', parse_response)

    def test_413_without_actor_id_leaves_submission_idle_and_draft_editable(self):
        helper = (ROOT / "homebox-ui/overlay/lib/feedback-report-state.js").resolve().as_uri()
        identity = (ROOT / "homebox-ui/overlay/lib/feedback-report-identity.js").resolve().as_uri()
        page = (ROOT / "homebox-ui/overlay/pages/feedback.vue").read_text()
        self.assertIn("recoverFeedbackSubmissionError", page)
        script = f'''import {{ recoverFeedbackSubmissionError }} from "{helper}";
import {{ persistFeedbackStatus }} from "{identity}";
const capturedResult = {{error:"The report request is too large."}};
const recovered = recoverFeedbackSubmissionError(capturedResult, 413);
const ui = {{status:"sending", error:""}};
if (recovered) Object.assign(ui, recovered);
const entries = new Map();
const storage = {{setItem(key, value) {{entries.set(key, value);}}, removeItem(key) {{entries.delete(key);}}}};
const draft = {{requestId:"req-a",type:"bug",description:"A saved report description"}};
persistFeedbackStatus(storage, "draft-a", draft, ui.status);
if (ui.status !== "idle" || ui.error !== "The report request is too large.") process.exit(1);
if (entries.get("draft-a") !== JSON.stringify(draft)) process.exit(2);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_deferred_response_after_cross_tab_account_change_cannot_mutate_other_draft(self):
        helper = (ROOT / "homebox-ui/overlay/lib/feedback-report-identity.js").resolve().as_uri()
        script = f'''import {{ feedbackActionIsCurrent }} from "{helper}";
let current = {{actorId:"user-a", draftKey:"draft-a", requestId:"req-a"}};
let resolve;
const pending = new Promise(done => resolve = done);
const capture = {{...current}};
let visibleDraft = "draft-a";
const action = pending.then(() => {{
  if (feedbackActionIsCurrent(capture, current)) visibleDraft = "response-a";
}});
current = {{actorId:"user-b", draftKey:"draft-b", requestId:"req-b"}};
visibleDraft = "draft-b";
resolve();
await action;
if (visibleDraft !== "draft-b") process.exit(1);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_storage_quota_error_is_a_failed_save_and_does_not_allow_submission(self):
        helper = (ROOT / "homebox-ui/overlay/lib/feedback-report-identity.js").resolve().as_uri()
        script = f'''import {{ writeFeedbackDraft }} from "{helper}";
const storage = {{ setItem() {{ throw new DOMException("quota exceeded", "QuotaExceededError"); }} }};
const draft = {{description:"retained in memory"}};
const saved = writeFeedbackDraft(storage, "draft-a", draft);
if (saved) process.exit(1);
if (draft.description !== "retained in memory") process.exit(2);
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_server_idempotency_database_is_in_the_checkpointed_backup_set(self):
        gateway = (ROOT / "deploy/workshop-gateway.py").read_text()
        backup = (ROOT / "deploy/backup-deployment.py").read_text()
        database = "work/ops/feedback-reports.db"
        self.assertIn("'work' / 'ops' / 'feedback-reports.db'", gateway)
        self.assertIn(repr(database), backup)


if __name__ == "__main__":
    unittest.main()
