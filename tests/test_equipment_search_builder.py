import importlib.util
import inspect
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('build_homebox_ui', ROOT / 'deploy/build-homebox-ui.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class EquipmentSearchBuilderTests(unittest.TestCase):
    def test_assigned_id_lookup_and_exact_miss_resolution_are_injected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'pages/item/[id]').mkdir(parents=True)
            (root / 'components/Item/View/table').mkdir(parents=True)
            (root / 'pages/items.vue').write_text('''  import type { LocationQueryRaw } from "vue-router";
  const api = useUserApi();
  async function search() {
    if (searchLocked.value) {
      return;
    }

    loading.value = true;
    const { data, error } = await api.items.getAll({
      q: query.value || "",
      fields,
    });

    function resetItems() {
      items.value = [];
    }
    if (!data.items || data.items.length === 0) {
      resetItems();
      return;
    }
    total.value = data.total;
    items.value = data.items;
  }
  watchDebounced([page, pageSize, query, selectedTags, selectedLocations], search, { debounce: 250, maxWait: 1000 });
''')
            (root / 'pages/item/[id]/index.vue').write_text('''  const api = useUserApi();
  const { data: item, refresh } = useAsyncData(itemId.value, async () => {
    const { data, error } = await api.items.get(itemId.value);
    if (error) {
      toast.error(t("items.toast.failed_load_item"));
      navigateTo("/home");
      return;
    }
    return data;
  });
          <div v-if="item.displayId" class="flex items-center gap-2 px-6 pb-2"><span class="text-sm text-muted-foreground" title="Generated from item type and full storage path; regenerated when the item moves.">Display ID</span><code class="font-mono font-semibold">{{ item.displayId }}</code><CopyText :text="item.displayId" :icon-size="16" /></div>
''')
            (root / 'components/Item/View/table/columns.ts').write_text('    {\n      id: "name",\n')
            (root / 'components/Item/View/table/data-table.vue').write_text('const defaultVisible = ["name", "quantity", "insured", "purchasePrice"];')
            previous = builder.BUILD
            builder.BUILD = root
            try:
                builder.equipment_assigned_ids_frontend()
            finally:
                builder.BUILD = previous
            search = (root / 'pages/items.vue').read_text()
            detail = (root / 'pages/item/[id]/index.vue').read_text()
            columns = (root / 'components/Item/View/table/columns.ts').read_text()
            table = (root / 'components/Item/View/table/data-table.vue').read_text()
            self.assertNotIn('equipment/ids/resolve?display_id=', search)
            self.assertIn('equipmentWorkshop.request("equipment/ids/resolve", { display_id: displayId })', search)
            self.assertIn('resolveAssignedIdAfterNativeMiss', search)
            self.assertIn('searchRevision', search)
            self.assertIn('searchedQuery', search)
            self.assertIn('q: searchedQuery || ""', search)
            self.assertIn('if (revision !== searchRevision || searchedQuery !== query.value) return;', search)
            self.assertIn('projectAssignedDisplayIds(data.items, assignmentMap)', search)
            self.assertIn('matchInventoryCustomFields', search)
            self.assertIn('equipment/ids?entity_ids=', detail)
            self.assertIn('effectiveDisplayId', detail)
            self.assertIn('item.value?.displayId', detail)  # Native legacy fallback.
            self.assertIn('id: "displayId"', columns)
            self.assertIn('"displayId", "thumbnail", "equipmentStatus", "location", "name"', table)
            self.assertNotIn('"insured"', table)
            self.assertNotIn('"purchasePrice"', table)

    def test_inventory_search_projection_matches_custom_fields_on_projected_records(self):
        projection = inspect.getsource(builder.grouped_inventory_frontend)
        self.assertIn('matchInventoryCustomFields(projected, searchedQuery)', projection)
        self.assertIn('const projected = projectAssignedDisplayIds(enriched, assignmentMap);', projection)
        self.assertIn('equipmentRows = fullRows || [];', projection)


if __name__ == '__main__':
    unittest.main()
