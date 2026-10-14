import unittest
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


class FeedbackUiContractTests(unittest.TestCase):
    def test_report_is_linked_from_the_collapsed_more_navigation(self):
        builder = (ROOT / "deploy/build-homebox-ui.py").read_text()
        self.assertIn('{ id: 92, name: computed(() => "Report feedback"), to: "/feedback"', builder)

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
        self.assertIn('"/ccrate-api/feedback"', page)
        self.assertNotIn("CCRATE_GITHUB_TOKEN", page)

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
