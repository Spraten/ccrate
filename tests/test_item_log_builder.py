"""Checked upstream insertion for the native item Log & notes disclosure."""
import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('build_homebox_ui', ROOT/'deploy/build-homebox-ui.py')
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class ItemLogBuilderTests(unittest.TestCase):
    def test_adds_one_log_component_after_native_item_details(self):
        with tempfile.TemporaryDirectory() as directory:
            build = pathlib.Path(directory)
            page = build/'pages/item/[id]/index.vue'
            page.parent.mkdir(parents=True)
            upstream = ROOT/'upstream/homebox/frontend/pages/item/[id]/index.vue'
            page.write_bytes(upstream.read_bytes())
            old_build = BUILDER.BUILD
            BUILDER.BUILD = build
            try:
                BUILDER.item_log_frontend()
            finally:
                BUILDER.BUILD = old_build
            result = page.read_text()
            self.assertEqual(result.count('import WorkshopItemLog from "@/components/Workshop/ItemLog.vue";'), 1)
            self.assertEqual(result.count('<WorkshopItemLog v-if="!hasNested" :item-id="itemId" />'), 1)
            self.assertNotIn('<WorkshopItemLog :item-id="itemId" />', result)
            details = result.index('          </DetailsSection>')
            display_id = result.index('<div v-if="item.displayId"')
            short_code = result.index('<div v-if="item.shortCode"')
            card_end = result.index('        </BaseCard>', details)
            log = result.index('<WorkshopItemLog v-if="!hasNested" :item-id="itemId" />')
            attachments = result.index('<!-- anything in this is not rendered if on another page -->', card_end)
            self.assertLess(details, display_id)
            self.assertLess(display_id, short_code)
            self.assertLess(short_code, card_end)
            self.assertLess(card_end, log)
            self.assertLess(log, attachments)

    def test_disclosure_preserves_loaded_window_plaintext_and_filter_contract(self):
        component = (ROOT/'homebox-ui/overlay/components/Workshop/ItemLog.vue').read_text()
        self.assertIn('<details data-testid="item-log" class="rounded-lg border bg-card shadow-xl"', component)
        self.assertNotIn('<details open', component)
        self.assertIn('Filters apply to the loaded companion records (up to 100 newest requests); older activity and unjournaled native changes are not included.', component)
        self.assertIn('No matches in loaded history.', component)
        self.assertEqual(component.count('type="datetime-local"'), 2)
        self.assertIn('row.status === "completed" && row.confirmed_at', component)
        self.assertIn('row.actor_id !== personFilter.value', component)
        self.assertIn('row.source}:${row.id', component)
        self.assertIn('class="whitespace-pre-wrap"', component)
        self.assertNotIn('v-html', component)


if __name__ == '__main__':
    unittest.main()
