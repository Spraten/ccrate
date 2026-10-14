import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class DisplayIDContractTests(unittest.TestCase):
    def test_backend_derives_full_path_and_keeps_native_identity_separate(self):
        source = (ROOT / 'homebox-backend/repo_display_ids.go').read_text()
        tests = (ROOT / 'homebox-backend/repo_display_ids_test.go').read_text()
        builder = (ROOT / 'deploy/build-homebox-backend.py').read_text()
        self.assertIn('formatDisplayID(typeName, path, items[i].AssetID, items[i].ID)', source)
        self.assertIn('"A"+strconv.FormatInt(int64(assetID), 10)', source)
        self.assertIn('"U"+compactUUID[:8]', source)
        self.assertIn('func isDisplayIDSearch(value string) bool', source)
        self.assertIn('formatDisplayID(typeName, path, items[i].AssetID, items[i].ID)', source)
        self.assertIn('WithParent().WithEntityType()', source)
        self.assertIn('entity.HasGroupWith(group.ID(gid))', source)
        self.assertIn("r.GetOneByGroup(ctx, gid, result.ID)", builder)
        self.assertIn("r.GetOneByGroup(ctx, gid, newEntityID)", builder)
        self.assertIn('BIN-D-GC-C-1', tests)
        self.assertIn('TestFormatDisplayIDUsesUUIDSuffixWhenNativeAssetIDIsUnassigned', tests)
        self.assertIn('require.NotEqual(t, item.DisplayID, duplicateItem.DisplayID)', tests)
        self.assertIn('originalUUID, originalAssetID, originalShortCode', tests)
        self.assertIn("schemas[name]['properties']['displayId']", builder)

    def test_item_details_search_and_label_designer_use_display_id(self):
        backend = (ROOT / 'deploy/build-homebox-backend.py').read_text()
        details = (ROOT / 'deploy/build-homebox-ui.py').read_text()
        designer = (ROOT / 'homebox-ui/overlay/components/Workshop/LabelDesigner.vue').read_text()
        editor = (ROOT / 'label-ui/src/editor-host.ts').read_text()
        label_backend = (ROOT / 'ops/label_layouts.py').read_text()
        label_tool = (ROOT / 'label-ui/patches/0002-label-editor-controls.patch').read_text()
        self.assertIn('isDisplayIDSearch(q.Search)', backend)
        self.assertNotIn('q.AssetID = id', backend)
        self.assertIn('EqualFold(item.DisplayID, displayIDSearch)', backend)
        self.assertIn('displayIDSearch == "" && (q.Page != -1 || q.PageSize != -1)', backend)
        self.assertIn('entities[offset:end]', backend)
        self.assertIn('item.displayId', details)
        self.assertIn('display_id: props.selectedItem.displayId || ""', designer)
        self.assertIn('display_id: nextDisplayId', editor)
        self.assertIn("'display_id':display_id", label_backend)
        self.assertIn("createText(place, '{{display_id}}')", label_tool)


if __name__ == '__main__':
    unittest.main()
