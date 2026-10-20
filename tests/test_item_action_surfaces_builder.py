import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('build_homebox_ui', ROOT / 'deploy/build-homebox-ui.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ItemActionSurfacesBuilderTests(unittest.TestCase):
    def test_native_layout_and_table_mount_shared_actions_per_exact_item(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'layouts').mkdir()
            (root / 'components/Item/View/table').mkdir(parents=True)
            (root / 'layouts/default.vue').write_text('''<template><div id="app">
    <ModalConfirm /><SidebarInset></SidebarInset></div></template>
<script lang="ts" setup>
</script>''')
            (root / 'components/Item/View/table/table-view.vue').write_text('''<script setup lang="ts">
  import DataTableExpandedRow from "./data-table-expanded-row.vue";
</script>
<template><TableCell v-for="cell in row.getVisibleCells()"><FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" /></TableCell></template>''')
            (root / 'components/Item/View/table/card-view.vue').write_text('''<script setup lang="ts">
  import DropdownAction from "./data-table-dropdown.vue";
</script>
<template>
    <ItemCard
      v-for="item in table.getRowModel().rows"
      :key="item.original.id"
      :item="item.original"
      :table-row="preferences.quickActions.enabled ? item : undefined"
      :location-flat-tree="locationFlatTree"
    /></template>''')
            previous = builder.BUILD
            builder.BUILD = root
            try:
                builder.item_action_surfaces_frontend()
            finally:
                builder.BUILD = previous
            layout = (root / 'layouts/default.vue').read_text()
            table = (root / 'components/Item/View/table/table-view.vue').read_text()
            card = (root / 'components/Item/View/table/card-view.vue').read_text()
            self.assertIn('import ItemActionHost from', layout)
            self.assertEqual(layout.count('<ItemActionHost'), 1)
            self.assertIn('ItemQuickActions', table)
            self.assertIn(':item-id="row.original.id"', table)
            self.assertIn('ItemQuickActions', card)
            self.assertIn(':item-id="item.original.id"', card)

    def test_action_callback_is_wired_to_child_group_loans_and_map_entity_sources(self):
        overlays = ROOT / 'homebox-ui/overlay'
        child_contents = (overlays / 'components/Location/ChildContents.vue').read_text()
        inventory_links = (overlays / 'components/InventoryUnitActionLinks.vue').read_text()
        loans = (overlays / 'components/Workshop/ItemLoans.vue').read_text()
        workshop = (overlays / 'lib/workshop-tools.js').read_text()
        route = (overlays / 'pages/workshop/[tool].vue').read_text()
        self.assertIn('<ItemQuickActions', child_contents)
        self.assertIn('item-id="item.id"', child_contents)
        self.assertIn('<ItemQuickActions', inventory_links)
        self.assertIn('<ItemQuickActions', loans)
        self.assertIn('activityMode?: "compact" | "details" | "all"', loans)
        self.assertIn('props.activityMode === "compact"', loans)
        self.assertIn('compactActivity.value ? 1 : 5', loans)
        self.assertIn('props.activityMode === "all"', loans)
        self.assertIn('v-if="compactActivity"', loans)
        self.assertIn('Recent activity notes', loans)
        self.assertIn('<Button v-if="compactActivity"', loans, 'only compact mode links to the detailed activity view')
        detail_page = (overlays / 'pages/item/[id]/index/loans.vue').read_text()
        self.assertIn('activity-mode="details"', detail_page)
        self.assertIn('itemActions.open(request, trigger)', route)
        self.assertIn('itemActionControls(p,row.entity_id)', workshop)
        self.assertIn('if(!object?.location_id', workshop, 'drawing-only shapes return before exposing native actions')
        self.assertIn('if(!isLocation)itemActionControls(details,targetId)', workshop)


if __name__ == '__main__':
    unittest.main()
