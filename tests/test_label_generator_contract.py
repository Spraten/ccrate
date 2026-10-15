import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class LabelGeneratorContractTests(unittest.TestCase):
    def test_template_save_recovery_checks_its_own_idempotency_result(self):
        workflow = (ROOT / 'homebox-ui/overlay/lib/workshop-tools.js').read_text(encoding='utf-8')
        designer = (ROOT / 'homebox-ui/overlay/components/Workshop/LabelDesigner.vue').read_text(encoding='utf-8')
        self.assertIn("p.path==='labels/templates/save'", workflow)
        self.assertIn("api('labels/templates/result',{request_key:p.key}", workflow)
        self.assertIn('if(result){removePending(p.key)', workflow)
        self.assertIn('action === "labels/templates/result" && result && typeof data?.request_key === "string"', designer)
        self.assertIn('workshop.confirmTemplateSave(data.request_key)', designer)

    def test_print_failures_are_visible_and_only_uncertain_outcomes_lock_retry(self):
        component = (ROOT / 'homebox-ui/overlay/components/Workshop/LabelGenerator.vue').read_text(encoding='utf-8')
        workflow = (ROOT / 'homebox-ui/overlay/lib/workshop-tools.js').read_text(encoding='utf-8')
        self.assertIn('workspace.printError', component)
        self.assertIn('workspace.printUncertain', component)
        self.assertIn('workspace.printLocked || workspace.printedReviewIds.includes(row.review_id)', component)
        self.assertIn("workspace.printError && !workspace.printUncertain ? 'Review again before retrying'", component)
        self.assertIn(':disabled="workspace.busy || workspace.printLocked || workspace.printedReviewIds.includes(row.review_id) || workspace.printedEntityIds?.includes(row.entity_id)"', component)
        self.assertIn('pendingLabelPrint(pending())', workflow)
        self.assertIn('labelPrintFailure(error,pending(),requestKey,workspace)', workflow)
        self.assertIn('labelReviewCanPrint(workspace,entityId,reviewId)', workflow)
        self.assertIn('if(state.invalidateReview){', workflow, 'a confirmed-unsent print failure must invalidate its old review ID before an explicit retry')
        self.assertIn('clearReviews(false)', workflow, 'failed review invalidation must retain completed physical prints in a multi-item queue')
        self.assertIn('workspace.printedEntityIds?.includes(row.entity_id)', component, 'a fresh preview must not offer labels that already printed before a later queue failure')
        self.assertIn("invalidateReview: !uncertain", (ROOT / 'homebox-ui/overlay/lib/label-print-recovery.js').read_text(encoding='utf-8'))
        self.assertIn('workspace.actions.recovery()', component)

    def test_routine_printing_keeps_in_context_preview_and_physical_confirmation(self):
        component = (ROOT / 'homebox-ui/overlay/components/Workshop/LabelGenerator.vue').read_text(encoding='utf-8')
        workflow = (ROOT / 'homebox-ui/overlay/lib/workshop-tools.js').read_text(encoding='utf-8')
        self.assertIn('Preview selected labels', component)
        self.assertIn('Preview and print', component)
        self.assertIn('Print label', component)
        self.assertNotIn('Review selected labels', component)
        self.assertNotIn('Reviewed labels', component)
        self.assertIn('@click="workspace.actions.printItem(row.entity_id, row.review_id)"', component)
        self.assertIn('workspace.printedEntityIds?.includes(row.entity_id)', component)
        self.assertIn('Preview labels here, then print each one from its card.', component)
        print_action = workflow.split('printItem(entityId,reviewId){', 1)[1].split('async compose(){', 1)[0]
        self.assertIn("openDialog('Confirm Pi label print'", print_action)
        self.assertIn("button('Cancel',()=>closeDialog())", print_action)
        self.assertIn("button('Confirm one Pi print'", print_action)
        self.assertLess(print_action.index("button('Confirm one Pi print'"), print_action.index("write('labels/print'"))
        self.assertIn('version!==reviewRevision||identityAtReview!==context?.identity', print_action)
        self.assertLess(print_action.index('version!==reviewRevision||identityAtReview!==context?.identity'), print_action.index("write('labels/print'"))
        self.assertIn('queueStopped||queueSending', print_action)
        self.assertIn('workspace.printedReviewIds.includes(reviewId)', print_action)
        self.assertIn('request_key:requestKey', print_action)
        self.assertIn("write('labels/print'", print_action)

    def test_generated_asset_id_is_searchable_and_visible_in_label_selection(self):
        component = (ROOT / 'homebox-ui/overlay/components/Workshop/LabelGenerator.vue').read_text(encoding='utf-8')
        self.assertIn('displayId?: string', component)
        self.assertIn('${item.displayId || ""}', component)
        self.assertIn('Generated ID · {{ item.displayId }}', component)

    def test_generator_uses_native_review_and_export_flow(self):
        component = (ROOT / 'homebox-ui/overlay/components/Workshop/LabelGenerator.vue').read_text(encoding='utf-8')
        route = (ROOT / 'homebox-ui/overlay/pages/workshop/[tool].vue').read_text(encoding='utf-8')
        workflow = (ROOT / 'homebox-ui/overlay/lib/workshop-tools.js').read_text(encoding='utf-8')
        self.assertIn('Preview selected labels', component)
        self.assertIn('Compose Letter sheet', component)
        self.assertIn('Download Letter PDF', component)
        self.assertIn(':disabled="!canReview"', component)
        self.assertIn(':disabled="!canCompose || workspace.busy"', component)
        self.assertIn(':disabled="!workspace.pages.length || workspace.busy"', component)
        self.assertIn('LabelDesigner', component)
        self.assertIn('shortCode?: string', component)
        self.assertIn('Short code', component)
        self.assertIn('HomeSortStuff', component)
        self.assertIn('<LabelGenerator v-if="tool === \'labels\'"', route)
        self.assertIn("api('labels/preview'", workflow)
        self.assertIn("api('labels/paper'", workflow)
        self.assertIn("write('labels/print'", workflow)
        self.assertIn('labelWorkspace=labelWorkspaceChanged(labelWorkspace)||labelWorkspace', workflow)
        self.assertIn('workspace.selectedIds=[...ids]', workflow)
        self.assertIn('applyLabelPreview(workspace,ids,result)', workflow)
        self.assertIn('workspace.printedReviewIds.includes(reviewId)', workflow)
        self.assertIn('labelWorkspaceChanged(null', workflow)
        self.assertIn("if (action !== \"labels/templates/save\")", (ROOT / 'homebox-ui/overlay/components/Workshop/LabelDesigner.vue').read_text(encoding='utf-8'))
        editor = (ROOT / 'label-ui/src/editor-host.ts').read_text(encoding='utf-8')
        self.assertIn('nextShortCode', editor)
        self.assertIn('nextShortCode !== sampleShortCode.value', editor)
        self.assertIn('draftPreview.invalidate(); closePreview()', editor)
        self.assertIn('short_code', editor)
        designer = (ROOT / 'homebox-ui/overlay/components/Workshop/LabelDesigner.vue').read_text(encoding='utf-8')
        self.assertIn('shortCode?: string', designer)
        self.assertIn('short_code:', designer)
        patch = (ROOT / 'label-ui/patches/0002-label-editor-controls.patch').read_text(encoding='utf-8')
        self.assertIn("key: 'short-code'", patch)
        self.assertIn("createText(place, '{{short_code}}')", patch)
        self.assertIn("labelKey: 'palette.shortCode'", patch)
        self.assertIn("shortCode:item.shortCode||''", workflow)
        self.assertIn("'Blank design'", editor)
        self.assertIn("Paper size: ${document.value.page.widthMm} × ${document.value.page.heightMm} mm", editor)
        self.assertIn("label: 'Starter designs'", editor)
        self.assertIn("templateProfile(t) === profile.value", editor)

    def test_reference_license_and_attribution_are_retained(self):
        license_file = ROOT / 'homebox-ui/HOMESORTSTUFF-LICENSE.txt'
        self.assertTrue(license_file.is_file())
        self.assertIn('GNU AFFERO GENERAL PUBLIC LICENSE', license_file.read_text(encoding='utf-8'))
        readme = (ROOT / 'homebox-ui/README.md').read_text(encoding='utf-8')
        self.assertIn('HomeSortStuff', readme)
        self.assertIn('85b96e5060a48dd11db24addfbc63407eed4e74c', readme)


if __name__ == '__main__':
    unittest.main()
