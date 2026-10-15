"""Guard the pinned API test transform for response-only item short codes."""
import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_homebox_ui", ROOT / "deploy/build-homebox-ui.py")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)

FIXTURES = '''    const item = { displayId: "BIN-D-GC-C-1", shortCode: "ABC-123" };
    const itemUpdate = {
      ...item,
      entityTypeId: item.entityType?.id || "",
      parentId: item.parent?.id || null,
    };
    const child1ItemUpdate = {
      ...child1Item,
      entityTypeId: child1Item.entityType?.id || "",
      parentId: parent.id,
    };
    const child2ItemUpdate = {
      ...child2Item,
      entityTypeId: child2Item.entityType?.id || "",
      parentId: parent.id,
    };
    const itemUpdate = {
      ...parent,
      entityTypeId: parent.entityType?.id || "",
      parentId: parentLocation.id,
    };
'''


class ItemUpdateTypecheckTransformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.old_build = BUILDER.BUILD
        BUILDER.BUILD = pathlib.Path(self.temp.name)
        target = BUILDER.BUILD / "lib/api/__test__/user/items.test.ts"
        target.parent.mkdir(parents=True)
        target.write_text(FIXTURES)

    def tearDown(self):
        BUILDER.BUILD = self.old_build
        self.temp.cleanup()

    def test_strips_output_only_short_code_from_each_update_spread(self):
        BUILDER.strip_item_response_short_codes_from_update_tests()
        result = (BUILDER.BUILD / "lib/api/__test__/user/items.test.ts").read_text()
        self.assertEqual(result.count("shortCode: omitted"), 4)
        self.assertNotIn("...item,", result)
        self.assertNotIn("...child1Item,", result)
        self.assertNotIn("...child2Item,", result)
        self.assertNotIn("...parent,", result)
        self.assertIn("...itemForUpdate,", result)
        self.assertIn("...child1ForUpdate,", result)
        self.assertIn("...child2ForUpdate,", result)
        self.assertIn("...parentForUpdate,", result)

    def test_fails_closed_when_an_upstream_anchor_changes(self):
        target = BUILDER.BUILD / "lib/api/__test__/user/items.test.ts"
        target.write_text(FIXTURES.replace(
            'entityTypeId: child2Item.entityType?.id || "",',
            'entityTypeID: child2Item.entityType?.id || "",',
        ))
        with self.assertRaisesRegex(RuntimeError, "exactly one item update fixture anchor"):
            BUILDER.strip_item_response_short_codes_from_update_tests()


if __name__ == "__main__":
    unittest.main()
