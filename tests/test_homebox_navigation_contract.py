"""Exercise the generated native sidebar against the pinned Homebox layout."""
import importlib.util
import os
import pathlib
import shutil
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_homebox_ui", ROOT / "deploy/build-homebox-ui.py")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)
UPSTREAM = pathlib.Path(os.environ.get("CCRATE_UPSTREAM_ROOT", ROOT / "upstream/homebox"))
LAYOUT = UPSTREAM / "frontend/layouts/default.vue"


@unittest.skipUnless(LAYOUT.is_file(), "Homebox submodule is unavailable; supply the pinned source path")
class HomeboxNavigationContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.build = pathlib.Path(self.temp.name)
        target = self.build / "layouts/default.vue"
        target.parent.mkdir(parents=True)
        shutil.copyfile(LAYOUT, target)
        self.old_build = BUILDER.BUILD
        BUILDER.BUILD = self.build
        BUILDER.navigation_frontend()
        self.output = target.read_text()

    def tearDown(self):
        BUILDER.BUILD = self.old_build
        self.temp.cleanup()

    def test_sidebar_is_right_aligned_without_leaving_a_left_gap(self):
        self.assertIn('<Sidebar side="right" collapsible="icon">', self.output)
        self.assertIn('<SidebarInset class="md:order-first min-h-dvh', self.output)

    def test_primary_entries_point_to_homebox_and_workshop_routes(self):
        self.assertLess(self.output.index("baseNav[0],"), self.output.index('name: computed(() => "Inventory")'))
        self.assertIn('{ ...baseNav[3], id: 1, name: computed(() => "Inventory") }', self.output)
        self.assertIn('name: computed(() => "Workshop"), to: "/workshop/map"', self.output)
        self.assertIn('name: computed(() => "Label"), to: "/workshop/labels"', self.output)
        self.assertIn('name: computed(() => "Users"), to: "/collection/members"', self.output)

    def test_more_is_closed_by_default_and_keeps_secondary_links(self):
        self.assertIn(':default-open="n.name.value !== \'More\'"', self.output)
        self.assertIn('name: computed(() => "More")', self.output)
        self.assertIn('to: "",', self.output)
        self.assertIn('<CollapsibleTrigger v-if="n.name.value === \'More\'" as-child><SidebarMenuButton', self.output)
        self.assertIn('<SidebarMenuLink v-else', self.output)
        self.assertIn('...nav.value.filter(v => v.name.value !== "More").map', self.output)
        self.assertNotIn('name: computed(() => "More"), to: "/home"', self.output)
        self.assertIn('...baseNav[7].collapsible!.filter(item => item.to !== "/collection/members")', self.output)
        self.assertIn('to: terminalURL.value', self.output)
        self.assertIn('action: openScanner', self.output)
        self.assertNotIn('<!-- makes scanner accessible easily if using legacy header -->', self.output)

    def test_workshop_manager_routes_keep_their_access_gate(self):
        self.assertIn('...(workshop.manager.value ? [["imports"', self.output)
        self.assertIn('workshopLinks.value.filter(([id]) => id !== "map" && id !== "labels")', self.output)


if __name__ == "__main__":
    unittest.main()
