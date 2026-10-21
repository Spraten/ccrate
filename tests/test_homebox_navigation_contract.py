"""Exercise the generated native sidebar against the pinned Homebox layout."""
import importlib.util
import os
import pathlib
import shutil
import subprocess
import tempfile
import re
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
        self.assertIn('computed<typeof baseNav>(() => {', self.output)
        self.assertIn('const navFor = (path: string) => baseNav.find(item => item.to === path);', self.output)
        self.assertIn('{ ...home!, id: 0 }', self.output)
        self.assertIn('{ ...inventory!, id: 1, name: computed(() => "Inventory") }', self.output)
        self.assertIn('name: computed(() => "Workshop"), to: "/workshop/map"', self.output)
        self.assertIn('name: computed(() => "Label"), to: "/workshop/labels"', self.output)
        self.assertIn('name: computed(() => "Users"), to: "/collection/members"', self.output)

    def test_equipment_id_codes_is_a_collection_member_workshop_entry(self):
        self.assertIn('["equipment-ids", "Equipment ID codes"]', self.output)
        self.assertIn('`/workshop/${id}`', self.output)
        page = (ROOT / 'homebox-ui/overlay/pages/workshop/[tool].vue').read_text()
        self.assertIn('"equipment-ids"', page)
        self.assertIn("tool.value === 'equipment-ids' ? 'Equipment ID codes'", page)

    def test_more_is_closed_by_default_and_keeps_secondary_links(self):
        self.assertIn(':default-open="n.name.value !== \'More\'"', self.output)
        self.assertIn('name: computed(() => "More")', self.output)
        self.assertIn('to: "",', self.output)
        self.assertIn('<CollapsibleTrigger v-if="n.name.value === \'More\'" as-child><SidebarMenuButton', self.output)
        self.assertIn('<SidebarMenuLink v-else', self.output)
        self.assertIn('...nav.value.filter(v => v.name.value !== "More").map', self.output)
        self.assertNotIn('name: computed(() => "More"), to: "/home"', self.output)
        self.assertIn('...collection!.collapsible!.filter(item => item.to !== "/collection/members")', self.output)
        self.assertNotIn('baseNav[7]', self.output)
        self.assertIn('item.to !== "/templates"', self.output)
        self.assertIn('...baseNav.filter(item => item !== home', self.output)
        self.assertIn('to: terminalURL.value', self.output)
        self.assertIn('action: openScanner', self.output)
        self.assertNotIn('<!-- makes scanner accessible easily if using legacy header -->', self.output)

    def test_reordered_base_navigation_without_templates_keeps_sidebar_valid(self):
        source = (ROOT / "deploy/build-homebox-ui.py").read_text()
        start = source.index('  const nav = computed<typeof baseNav>(() => {', source.index('def navigation_frontend'))
        end = source.index('\n  });', start) + len('\n  });')
        nav_code = source[start:end]
        nav_code = nav_code.replace('const nav = computed<typeof baseNav>(() => {', 'const nav = (() => {').replace('(path: string)', '(path)')
        nav_code = re.sub(r'([\w\]])!([,.)\]])', r'\1\2', nav_code)
        fixture = r'''const computed = fn => ({ value: fn() });
const route = { path: "/home" }, workshopLinks = { value: [] }, terminalURL = { value: "/terminal" };
const MdiWrench = "wrench", MdiTagMultiple = "tag", MdiFileDocumentMultiple = "file";
const t = value => value, openScanner = () => {};
const entry = (to, id, collapsible) => ({ to, id, icon: `icon-${id}`, name: computed(() => to), active: computed(() => false), ...(collapsible ? { collapsible } : {}) });
const child = to => ({ to, id: 100, name: computed(() => to), active: computed(() => false) });
const baseNav = [entry("/profile", 6), entry("/collection/members", 7, [child("/collection/members"), child("/collection/invites")]), entry("/locations", 1), entry("/home", 0), entry("/items", 3), entry("/tags", 2), entry("/maintenance", 4)];
NAV
const values = nav.map(item => item.to);
if (nav.some(item => !item || !item.icon)) throw Error("entry missing icon");
if (nav.filter(item => item.to === "/home").length !== 1) throw Error("duplicate Home");
const users = nav.find(item => item.name.value === "Users");
if (users?.icon !== "icon-7") throw Error("Users lost collection icon");
const more = nav.find(item => item.name.value === "More");
if (more.collapsible.some(item => item.to === "/home" || item.to === "/templates")) throw Error("excluded route in More");
if (!more.collapsible.some(item => item.to === "/collection/invites")) throw Error("collection link missing");'''.replace("NAV", nav_code[:-len("  });")] + "  })();")
        result = subprocess.run(["node", "-e", fixture], capture_output=True, text=True); self.assertEqual(result.returncode, 0, result.stderr)
        with_template = fixture.replace('entry("/maintenance", 4)]', 'entry("/maintenance", 4), entry("/templates", 5)]')
        result = subprocess.run(["node", "-e", with_template], capture_output=True, text=True); self.assertEqual(result.returncode, 0, result.stderr)

    def test_workshop_manager_routes_keep_their_access_gate(self):
        self.assertIn('["checkout-cart", "Checkout cart"]', self.output)
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
        self.assertIn('<DeviceStatus :enabled="true" class="shrink-0" />', self.output)
        self.assertNotIn('terminalHeader', self.output)
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

    def test_label_designer_refreshes_theme_tokens_after_palette_changes(self):
        component = (ROOT / "homebox-ui/overlay/components/Workshop/LabelDesigner.vue").read_text()
        self.assertIn("const { theme } = useTheme()", component)
        self.assertIn('watch(theme, () => { if (frame) frame.updateContext?.(editorContext()); }, { flush: "post" });', component)
        self.assertIn("watch(() => props.selectedItem", component)


if __name__ == "__main__":
    unittest.main()


class HomeboxShortCodeBuilderContractTests(unittest.TestCase):
    def test_native_item_and_create_modal_keep_readonly_short_code_contract(self):
        builder = (ROOT / 'deploy/build-homebox-ui.py').read_text()
        self.assertIn('item.shortCode', builder)
        self.assertIn('CopyText :text="item.shortCode"', builder)
        self.assertIn('v-model="form.modelNumber" label="Model number"', builder)
        self.assertIn('modelNumber: form.modelNumber?.trim() || undefined', builder)
        self.assertIn("export interface EntitySummary {\\n  displayId: string;\\n  shortCode: string;", builder)
        self.assertIn("export interface EntityOut {\\n  displayId: string;\\n  shortCode: string;", builder)
