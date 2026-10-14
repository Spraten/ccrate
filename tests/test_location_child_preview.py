"""Regression contract for the read-only child-location preview on details pages."""
import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_homebox_ui", ROOT / "deploy/build-homebox-ui.py")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class ChildLocationPreviewTests(unittest.TestCase):
    def test_location_detail_embeds_expandable_read_only_child_contents(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            previous_build = BUILDER.BUILD
            BUILDER.BUILD = pathlib.Path(directory) / "homebox-ui-build"
            try:
                BUILDER.prepare()
            finally:
                BUILDER.BUILD = previous_build

            page = (pathlib.Path(directory) / "homebox-ui-build/pages/location/[id]/index/index.vue").read_text()
            component = (pathlib.Path(directory) / "homebox-ui-build/components/Location/ChildContents.vue").read_text()
            self.assertIn("<ChildContents v-if=\"location && location.children?.length\" :locations=\"location.children\" />", page)
            self.assertNotIn('<LocationCard v-for="child in location.children"', page)
            self.assertIn('api.items.getAll({ parentIds: [locationId] })', component)
            self.assertIn('api.items.getLocation(locationId)', component)
            self.assertIn('v-if="location.itemCount > 0"', component)
            self.assertIn(':aria-expanded="stateFor(location.id).expanded"', component)
            self.assertIn('`/location/${encodeURIComponent(location.id)}`', component)
            self.assertIn('`/item/${encodeURIComponent(item.id)}`', component)
            self.assertIn('v-if="stateFor(location.id).loading"', component)
            self.assertIn('v-else-if="stateFor(location.id).error"', component)
            self.assertIn('v-else-if="stateFor(location.id).items.length === 0 && stateFor(location.id).children.length === 0"', component)
            self.assertIn('<ChildContents v-if="stateFor(location.id).children.length" :locations="stateFor(location.id).children" />', component)


if __name__ == "__main__":
    unittest.main()
