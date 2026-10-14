import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FeedbackUiContractTests(unittest.TestCase):
    def test_report_is_linked_from_the_collapsed_more_navigation(self):
        builder = (ROOT / "deploy/build-homebox-ui.py").read_text()
        self.assertIn('{ id: 92, name: computed(() => "Report feedback"), to: "/feedback"', builder)

    def test_page_keeps_request_identity_per_native_user_and_never_contains_a_github_token(self):
        page = (ROOT / "homebox-ui/overlay/pages/feedback.vue").read_text()
        self.assertIn('definePageMeta({ middleware: ["auth"] })', page)
        self.assertIn('`ccrate-feedback-draft:${auth.user.id}`', page)
        self.assertIn('"Idempotency-Key": requestId.value', page)
        self.assertIn('"/ccrate-api/feedback"', page)
        self.assertNotIn("CCRATE_GITHUB_TOKEN", page)

    def test_server_idempotency_database_is_in_the_checkpointed_backup_set(self):
        gateway = (ROOT / "deploy/workshop-gateway.py").read_text()
        backup = (ROOT / "deploy/backup-deployment.py").read_text()
        database = "work/ops/feedback-reports.db"
        self.assertIn("'work' / 'ops' / 'feedback-reports.db'", gateway)
        self.assertIn(repr(database), backup)


if __name__ == "__main__":
    unittest.main()
