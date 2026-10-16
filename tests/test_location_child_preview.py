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
    def test_child_item_preview_prefers_generated_display_id_with_native_fallback(self):
        component = (ROOT / "homebox-ui/overlay/components/Location/ChildContents.vue").read_text(encoding="utf-8")
        self.assertIn('v-if="item.displayId"', component)
        self.assertIn('Generated ID · {{ item.displayId }}', component)
        self.assertIn('v-else-if="item.assetId"', component)
        self.assertIn('{{ item.assetId }}', component)
        self.assertIn('class="min-w-0 flex-1"', component)
        self.assertIn('break-all', component)
        self.assertIn('×{{ item.quantity }}', component)

    def test_location_detail_embeds_expandable_read_only_child_contents(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            previous_build = BUILDER.BUILD
            build = pathlib.Path(directory) / "homebox-ui-build"
            BUILDER.BUILD = build
            location_page = build / "pages/location/[id]/index/index.vue"
            location_page.parent.mkdir(parents=True)
            location_page.write_text(
                '  import LocationCard from "~/components/Location/Card.vue";\n'
                '      <!-- Child locations -->\n'
                '      <section v-if="location && location.children && location.children.length > 0" class="mt-6">\n'
                '        <BaseSectionHeader class="mb-5"> {{ $t("locations.child_locations") }} </BaseSectionHeader>\n'
                '        <div class="grid grid-cols-1 gap-2 sm:grid-cols-3">\n'
                '          <LocationCard v-for="child in location.children" :key="child.id" :location="child" />\n'
                '        </div>\n'
                '      </section>'
            )
            try:
                BUILDER.location_child_contents_frontend()
            finally:
                BUILDER.BUILD = previous_build

            page = location_page.read_text()
            source_component = ROOT / "homebox-ui/overlay/components/Location/ChildContents.vue"
            component = source_component.read_text()
            self.assertIn("<ChildContents v-if=\"location && location.children?.length\" :locations=\"location.children\" />", page)
            self.assertNotIn('<LocationCard v-for="child in location.children"', page)
            self.assertIn('api.items.getAll({ parentIds: immediateChildIds, page, pageSize: 100, includeArchived: true })', component)
            self.assertIn('item.parent.id', component)
            self.assertIn('props.locations.map(location => location.id)', component)
            self.assertIn('const isRoot = props.depth === 0', component)
            self.assertIn('expanded: isRoot', component)
            self.assertIn('if (isRoot) {', component)
            self.assertIn('api.items.getLocation(locationId)', component)
            self.assertIn('v-if="location.itemCount > 0"', component)
            self.assertIn(':aria-expanded="stateFor(location.id).expanded"', component)
            self.assertIn('Collapse all bins', component)
            self.assertIn('Expand bins', component)
            self.assertIn(':aria-expanded="allExpanded"', component)
            self.assertIn('`/location/${encodeURIComponent(location.id)}`', component)
            self.assertIn('`/item/${encodeURIComponent(item.id)}`', component)
            self.assertIn('v-if="stateFor(location.id).loading"', component)
            self.assertIn('v-if="stateFor(location.id).error"', component)
            self.assertIn('directItems.get(location.id)?.length || 0', component)
            self.assertIn('<ChildContents v-if="stateFor(location.id).children.length" :locations="stateFor(location.id).children" :depth="props.depth + 1" />', component)


if __name__ == "__main__":
    unittest.main()
