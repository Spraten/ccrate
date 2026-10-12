import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class LabelGeneratorContractTests(unittest.TestCase):
    def test_generator_uses_native_review_and_export_flow(self):
        component = (ROOT / 'homebox-ui/overlay/components/Workshop/LabelGenerator.vue').read_text()
        route = (ROOT / 'homebox-ui/overlay/pages/workshop/[tool].vue').read_text()
        workflow = (ROOT / 'homebox-ui/overlay/lib/workshop-tools.js').read_text()
        self.assertIn('Review selected labels', component)
        self.assertIn('Compose reviewed Letter sheet', component)
        self.assertIn('Download reviewed PDF', component)
        self.assertIn(':disabled="!canReview"', component)
        self.assertIn(':disabled="!canCompose || workspace.busy"', component)
        self.assertIn(':disabled="!workspace.pages.length || workspace.busy"', component)
        self.assertIn('LabelDesigner', component)
        self.assertIn('HomeSortStuff', component)
        self.assertIn('<LabelGenerator v-if="tool === \'labels\'"', route)
        self.assertIn("api('labels/preview'", workflow)
        self.assertIn("api('labels/paper'", workflow)
        self.assertIn("write('labels/print'", workflow)
        self.assertIn('labelWorkspace=labelWorkspaceChanged(labelWorkspace)||labelWorkspace', workflow)
        self.assertIn('workspace.selectedIds=[...ids]', workflow)
        self.assertIn("entity_id:ids[index]", workflow)
        self.assertIn('workspace.printedReviewIds.includes(reviewId)', workflow)
        self.assertIn('labelWorkspaceChanged(null', workflow)
        self.assertIn("if (action !== \"labels/templates/save\")", (ROOT / 'homebox-ui/overlay/components/Workshop/LabelDesigner.vue').read_text())
        self.assertIn("!templates.value.some((t: any) => t.id === k)", (ROOT / 'label-ui/src/editor-host.ts').read_text())

    def test_reference_license_and_attribution_are_retained(self):
        license_file = ROOT / 'homebox-ui/HOMESORTSTUFF-LICENSE.txt'
        self.assertTrue(license_file.is_file())
        self.assertIn('GNU AFFERO GENERAL PUBLIC LICENSE', license_file.read_text())
        readme = (ROOT / 'homebox-ui/README.md').read_text()
        self.assertIn('HomeSortStuff', readme)
        self.assertIn('85b96e5060a48dd11db24addfbc63407eed4e74c', readme)


if __name__ == '__main__':
    unittest.main()
