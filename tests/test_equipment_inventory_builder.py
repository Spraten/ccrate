import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('build_homebox_ui', ROOT / 'deploy/build-homebox-ui.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class EquipmentInventoryBuilderTests(unittest.TestCase):
    def test_grouped_projection_fetches_full_filtered_result_and_keeps_native_manage_surface(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'pages').mkdir()
            (root / 'pages/items.vue').write_text('''  import type { LocationQueryRaw } from "vue-router";
  const items = ref<EntitySummary[]>([]);
  const total = ref(0);
  const pagination = proxyRefs({
    page,
    pageSize,
    totalSize: total,
    setPage: (newPage: number) => {
      page.value = newPage;
    },
  });
  async function search() {
    const searchedQuery = query.value;

    loading.value = true;
    const { data, error } = await api.items.getAll({
      q: searchedQuery || "",
      parentIds: locIDs.value,
      tags: tagIDs.value,
      negateTags: negateTags.value,
      onlyWithoutPhoto: onlyWithoutPhoto.value,
      onlyWithPhoto: onlyWithPhoto.value,
      includeArchived: includeArchived.value,
      page: page.value,
      pageSize: pageSize.value,
      orderBy: orderBy.value,
      fields,
    });
    function resetItems() {
      total.value = 0;
      items.value = [];
    }
    if (error) {
      resetItems();
      toast.error(t("items.toast.failed_search_items"));
      return;
    }
    let assignmentMap = {};
    try {
      assignmentMap = await fetchAssignedDisplayIds(data.items.map(item => item.id), ids =>
        equipmentWorkshop.request(`equipment/ids?entity_ids=${encodeURIComponent(ids.join(","))}`)
      );
    } catch { /* Keep native IDs if the optional catalog lookup is unavailable. */ }
    if (revision !== searchRevision || searchedQuery !== query.value) return;
    total.value = data.total;
    items.value = projectAssignedDisplayIds(data.items, assignmentMap);
  }
      <ItemViewSelectable
        :items="items"
        :location-flat-tree="locationFlatTree"
        :pagination="pagination"
        disable-sort
        @refresh="async () => search()"
      />
''')
            previous = builder.BUILD
            builder.BUILD = root
            try:
                builder.grouped_inventory_frontend()
            finally:
                builder.BUILD = previous
            page = (root / 'pages/items.vue').read_text()
            self.assertIn('loadAllFilteredInventory', page)
            self.assertIn('const nativeOptions = {', page)
            self.assertIn('parentIds: locIDs.value', page)
            self.assertIn('tags: tagIDs.value', page)
            self.assertIn('groupInventoryItems(projected, assignmentMap', page)
            self.assertIn('nativeManageItems', page)
            self.assertIn('nativePagination', page)
            self.assertIn('q: searchedQuery', page)
            self.assertIn('matchedEntityIds: [...matchingEntityIds]', page)
            self.assertIn('nativeTotal.value = managementMatches.length', page)
            self.assertIn('equipmentWorkshop.request<any[]>("equipment")', page)
            self.assertIn('loadInventoryActionStatuses(equipmentRows.map((row: any) => row.id)', page)
            self.assertIn('item-actions/status?ids=', page)
            self.assertIn('statuses as Record<string, any>)[item.id]?.availability', page)
            self.assertIn('buildInventoryStoragePath(item, locationById)', page)
            self.assertIn('history?entity=', page)
            self.assertIn('recentItemNotes(found.get(entityId) || [], entityId, 1)', page)
            self.assertIn('request.refresh', page)
            self.assertIn('@refresh-items="search"', page)
            self.assertIn('Math.min(4, request.entityIds.length)', page)
            self.assertIn('noteRequestVersions.begin(request.entityIds)', page)
            self.assertIn('noteRequestVersions.isCurrent(entityVersions, entityId)', page)
            self.assertIn('requestIdentity !== inventoryNotesIdentity', page)
            self.assertIn('finally {', page)
            self.assertIn('requestIdentity === inventoryNotesIdentity', page)
            self.assertIn('includeArchived: includeArchived.value', page)
            self.assertIn('onlyWithoutPhoto: onlyWithoutPhoto.value', page)
            self.assertIn('onlyWithPhoto: onlyWithPhoto.value', page)
            self.assertIn('negateTags: negateTags.value', page)
            self.assertNotIn('status: loan ? "checked_out"', page)
            component = (ROOT / 'homebox-ui/overlay/components/InventoryGroups.vue').read_text()
            self.assertIn('groupCounts(group).archived', component)
            self.assertIn('unit.storagePath', component)
            self.assertIn('unit.status', component)
            self.assertIn('inventoryNoteRequestKey(group.key, group.items.map(item => item.id))', component)
            self.assertIn("emit('update:page', lastPage)", component)
            self.assertIn('<InventoryGroups', page)
            self.assertIn('Manage matching native items', page)
            self.assertIn('inventoryNoteRequestKey(request.key, request.entityIds)', page)
            self.assertIn('page.value = Math.min(page.value', page)
            self.assertIn('noteLoadedGroups.value.has(noteKey)', page)


if __name__ == '__main__':
    unittest.main()
