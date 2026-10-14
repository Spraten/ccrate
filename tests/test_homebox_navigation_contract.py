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
        BUILDER.shell_frontend()
        self.output = target.read_text()

    def tearDown(self):
        BUILDER.BUILD = self.old_build
        self.temp.cleanup()

    def test_sidebar_is_left_aligned_in_native_provider_order(self):
        self.assertIn('<Sidebar side="left" collapsible="icon">', self.output)
        self.assertIn('<SidebarInset class="min-h-dvh', self.output)
        self.assertNotIn('md:order-first', self.output)

    def test_primary_entries_point_to_homebox_and_workshop_routes(self):
        self.assertIn('computed<typeof baseNav>(() => [', self.output)
        self.assertLess(self.output.index("baseNav[0]!,"), self.output.index('name: computed(() => "Inventory")'))
        self.assertIn('{ ...baseNav[3]!, id: 1, name: computed(() => "Inventory") }', self.output)
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
        self.assertIn('...baseNav[7]!.collapsible!.filter(item => item.to !== "/collection/members")', self.output)
        self.assertIn('to: terminalURL.value', self.output)
        self.assertIn('action: openScanner', self.output)
        self.assertNotIn('<!-- makes scanner accessible easily if using legacy header -->', self.output)

    def test_workshop_manager_routes_keep_their_access_gate(self):
        self.assertIn('...(workshop.manager.value ? [["imports"', self.output)
        self.assertIn('workshopLinks.value.filter(([id]) => id !== "map" && id !== "labels")', self.output)

    def test_compact_chrome_keeps_native_account_and_collection_controls(self):
        self.assertIn('aria-label="C-Crate home"', self.output)
        self.assertIn('<AppLogo aria-hidden="true" class="size-7 shrink-0" />', self.output)
        self.assertNotIn('group-data-[collapsible=icon]:hidden">C-Crate</span>', self.output)
        builder = (ROOT / "deploy/build-homebox-ui.py").read_text()
        self.assertIn('text-base font-bold group-data-[collapsible=icon]:hidden">C-Crate</span>', builder)
        self.assertIn('<CollectionSelector />', self.output)
        self.assertIn('data-testid="logout-button"', self.output)
        self.assertIn('hotkey="Shortcut: Ctrl+`"', self.output)
        self.assertNotIn('$t("global.welcome", { username: username })', self.output)
        self.assertNotIn('size-24', self.output)

    def test_quiet_header_keeps_labeled_search_scanner_and_device_status(self):
        self.assertIn('bg-card px-3 py-2', self.output)
        self.assertIn(':aria-label="$t(\'global.search\')"', self.output)
        self.assertIn(':aria-label="$t(\'menu.scanner\')"', self.output)
        self.assertIn('<DeviceStatus v-if="!preferences.displayLegacyHeader || !terminalHeader"', self.output)
        self.assertIn('<DeviceStatus v-if="preferences.displayLegacyHeader && terminalHeader"', self.output)
        self.assertIn('matchMedia("(min-width: 1024px)")', self.output)
        self.assertIn('<AppHeaderText class="h-6" />', self.output)

    def test_polish_palette_is_scoped_to_the_homebox_default_theme(self):
        css = (ROOT / "homebox-ui/overlay/assets/css/ccrate.css").read_text()
        builder = (ROOT / "deploy/build-homebox-ui.py").read_text()
        self.assertIn(":root.theme-homebox", css)
        self.assertNotIn(":root:not([data-theme])", css)
        self.assertIn("--primary: 139 16% 43%;", css)
        self.assertNotIn(".device-status__name", css)
        self.assertIn('"@/assets/css/ccrate.css"', builder)
        self.assertNotIn(".theme-dark", css)

    def test_container_geometry_is_independent_of_the_selected_theme(self):
        css = (ROOT / "homebox-ui/overlay/assets/css/ccrate.css").read_text()
        self.assertIn(":root #app .container", css)
        self.assertNotIn(":root.theme-homebox #app .container", css)


if __name__ == "__main__":
    unittest.main()


class HomeboxShortCodeBuilderContractTests(unittest.TestCase):
    def test_native_item_and_create_modal_keep_readonly_short_code_contract(self):
        builder = (ROOT / 'deploy/build-homebox-ui.py').read_text()
        self.assertIn('item.shortCode', builder)
        self.assertIn('CopyText :text="item.shortCode"', builder)
        self.assertIn('v-model="form.modelNumber" label="Model number"', builder)
        self.assertIn('modelNumber: form.modelNumber?.trim() || undefined', builder)
        self.assertIn("export interface EntitySummary {\\n  shortCode: string;", builder)
        self.assertIn("export interface EntityOut {\\n  shortCode: string;", builder)
