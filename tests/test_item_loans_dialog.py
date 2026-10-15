"""Guard review dialog close transitions against showing the wrong action."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ItemLoansDialogTests(unittest.TestCase):
    def test_closed_dialog_does_not_fall_through_to_administrative_return(self):
        component = (ROOT / "homebox-ui/overlay/components/Workshop/ItemLoans.vue").read_text()

        self.assertIn('v-if="mode === \'condition\'"', component)
        self.assertIn('v-else-if="mode === \'return\'"', component)
        self.assertIn('<template #actions><template v-if="mode !== null">', component)

    def test_dialog_title_uses_last_opened_action_during_close_transition(self):
        component = (ROOT / "homebox-ui/overlay/components/Workshop/ItemLoans.vue").read_text()

        self.assertIn('dialogKind = ref<"condition" | "return">("condition")', component)
        self.assertIn(':title="dialogKind === \'return\' ? \'Review administrative return\' : \'Review condition\'"', component)
        self.assertIn("dialogKind = 'condition'; mode = 'condition'", component)
        self.assertIn('dialogKind.value = "return"; mode.value = "return"', component)


if __name__ == "__main__":
    unittest.main()
