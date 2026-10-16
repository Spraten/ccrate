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
    def test_cabinet_filter_searches_loaded_fields_and_keeps_bin_context(self):
        component = (ROOT / "homebox-ui/overlay/components/Location/ChildContents.vue").read_text(encoding="utf-8")
        self.assertIn('aria-label="Filter loaded cabinet contents"', component)
        self.assertIn('v-model="filterText"', component)
        self.assertIn('Clear filter', component)
        self.assertIn('item.manufacturer', component)
        self.assertIn('item.modelNumber', component)
        self.assertIn('item.serialNumber', component)
        self.assertIn('location.name', component)
        self.assertIn('Search covers loaded cabinet contents only', component)
        self.assertIn('{{ locationPath(location.name) }}</NuxtLink>', component)
        self.assertIn('function matchesItem(item: EntitySummary)', component)
        self.assertIn('function matchesLocationName(location: LocationNode)', component)
        self.assertIn('function filteredLocations()', component)
        self.assertIn('if (!searchTerm.value) return props.locations', component)
        self.assertIn('v-for="location in filteredLocations()"', component)
        self.assertIn('Bin name match', component)
        self.assertIn('No loaded locations match this filter.', component)

    def test_bin_name_match_keeps_header_without_bypassing_item_filter(self):
        component = (ROOT / "homebox-ui/overlay/components/Location/ChildContents.vue").read_text(encoding="utf-8")
        self.assertIn('function matchesLocationName(location: LocationNode)', component)
        self.assertIn('return props.locations.filter(location => matchesLocationName(location) || visibleItems(location).length > 0)', component)
        self.assertIn('return itemsFor(location).filter(matchesItem)', component)
        self.assertNotIn('if (location.name.toLocaleLowerCase().includes(searchTerm.value)) return items', component)
        self.assertIn('v-if="matchesLocationName(location)"', component)
        self.assertIn('@click="filterText = \'\'"', component)

    def test_root_loads_location_hierarchy_without_item_requests_and_expand_retries_details(self):
        component = (ROOT / "homebox-ui/overlay/components/Location/ChildContents.vue").read_text(encoding="utf-8")
        self.assertIn('for (const location of props.locations) void loadDetail(location.id)', component)
        self.assertIn('if (expanded && !state.loaded) void loadDetail(location.id)', component)
        self.assertIn('if (!isRoot) {', component)
        self.assertIn('onMounted(() => {\n    if (!isRoot) return;', component)

    def test_nested_contents_stay_lazy_and_failures_keep_retryable_rows(self):
        component = (ROOT / "homebox-ui/overlay/components/Location/ChildContents.vue").read_text(encoding="utf-8")
        self.assertIn('if (state.expanded && !isRoot) void loadDetail(locationId)', component)
        self.assertIn('api.items.getLocation(locationId)', component)
        self.assertIn('state.items = collected.slice()', component)
        self.assertIn('Some location contents could not be loaded. Results may be incomplete.', component)
        self.assertIn('function retryBatch()', component)
        self.assertIn('function retryDetail(locationId: string)', component)
        self.assertIn('This location is empty.', component)
        self.assertIn('Could not load this location\'s details. Try again.', component)
        self.assertIn('`/location/${encodeURIComponent(location.id)}`', component)
        self.assertIn('`/item/${encodeURIComponent(item.id)}`', component)

    def test_child_item_preview_prefers_generated_display_id_with_native_fallback(self):
        component = (ROOT / "homebox-ui/overlay/components/Location/ChildContents.vue").read_text(encoding="utf-8")
        self.assertIn('v-if="item.displayId"', component)
        self.assertIn('Generated ID · {{ item.displayId }}', component)
        self.assertIn('v-else-if="item.assetId"', component)
        self.assertIn('{{ item.assetId }}', component)
        self.assertIn('class="min-w-0 flex-1"', component)
        self.assertIn('break-all', component)
        self.assertIn('×{{ item.quantity }}', component)

    def test_archived_item_has_visible_status(self):
        component = (ROOT / "homebox-ui/overlay/components/Location/ChildContents.vue").read_text(encoding="utf-8")
        self.assertIn('v-if="item.archived"', component)
        self.assertIn('>Archived</span>', component)

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
            self.assertIn('let received = 0', component)
            self.assertIn('if (!response.data.items.length && received < total) throw new Error(\"incomplete page\")', component)
            self.assertIn('onMounted(() => {\n    if (!isRoot) return;\n    for (const location of props.locations) directItems.set(location.id, []);\n    void loadItems();\n    for (const location of props.locations) void loadDetail(location.id);\n  });', component)
            self.assertIn('for (const location of props.locations) void loadDetail(location.id)', component)
            self.assertIn('if (state.expanded && !isRoot) void loadDetail(locationId)', component)
            self.assertIn('props.locations.map(location => location.id)', component)
            self.assertIn('const isRoot = props.depth === 0', component)
            self.assertIn('expanded: isRoot', component)
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
            self.assertIn('itemsFor(location).length === 0', component)
            self.assertIn('<ChildContents v-if="stateFor(location.id).children.length" :locations="stateFor(location.id).children" :depth="props.depth + 1" :filter="searchTerm" :parent-path="locationPath(location.name)" />', component)


if __name__ == "__main__":
    unittest.main()
