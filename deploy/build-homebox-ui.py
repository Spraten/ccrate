#!/usr/bin/env python3
"""Build a native Homebox frontend overlay without modifying the upstream checkout.

Install the pinned frontend dependencies in work/homebox-ui-build first. A
fresh --build-root installs from its copied lockfile. Output stays staged until
a verified release is selected by work/homebox-ui-current.
"""
import argparse
import os
import json
import pathlib
import shutil
import subprocess
import sys
import re
import threading
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(pathlib.Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from homebox_patchset import source_commit
BUILD = ROOT / 'work/homebox-ui-build'
TOOLCHAIN_ROOT = ROOT / 'work/toolchains'
UPSTREAM_ROOT = ROOT


def replace(path, old, new):
    target = BUILD / path
    source = target.read_text()
    if source.count(old) != 1:
        raise RuntimeError(f'Upstream changed: expected one patch anchor in {path}')
    target.write_text(source.replace(old, new))


def configure_ui_component_discovery():
    # Keep shadcn's TypeScript barrels importable while Nuxt auto-discovers only
    # the Vue components they intentionally export. Register after shadcn-nuxt
    # so its components:dirs hook has already appended its directory.
    replace(
        'nuxt.config.ts',
        '''  modules: [
    "@nuxtjs/tailwindcss",
    "@pinia/nuxt",
    "@vueuse/nuxt",
    "@vite-pwa/nuxt",
    "unplugin-icons/nuxt",
    "shadcn-nuxt",
    "@nuxt/eslint",
  ],''',
        '''  modules: [
    "@nuxtjs/tailwindcss",
    "@pinia/nuxt",
    "@vueuse/nuxt",
    "@vite-pwa/nuxt",
    "unplugin-icons/nuxt",
    "shadcn-nuxt",
    "@nuxt/eslint",
    (_options, nuxt) => {
      nuxt.hook("components:dirs", dirs => {
        for (let index = 0; index < dirs.length; index++) {
          const source = dirs[index];
          if (!source) continue;
          const dir = typeof source === "string" ? { path: source, extensions: [] } : source;
          if (dir.path.replaceAll("\\\\", "/").includes("components/ui")) {
            dir.extensions = ["vue"];
            dirs[index] = dir;
          }
        }
      });
    },
  ],''',
    )


def filter_known_wasi_warning(output):
    """Drop only the exact Node WASI notice known to accompany the Pi fallback."""
    return re.sub(
        r'(?m)^ERROR \(node:\d+\) ExperimentalWarning: WASI is an experimental feature and might change at any time(?:\r?\n|$)',
        '',
        output,
    )


def has_frontend_tool_failure(output):
    """Recognize invocation failures that must never be waived as upstream TS errors."""
    return re.search(
        r'(?im)^(?:ERR_PNPM_[A-Z0-9_]+\b|\s*ERROR\s+spawn\b|Error:|Error \[ERR_[A-Z_]+\]:|'
        r'Error: (?:Cannot find module|Cannot find package|spawn .* ENOENT)|'
        r'.* is not recognized as an internal or external command\.?)',
        output,
    ) is not None


def is_only_known_upstream_typecheck_failure(output, baseline, pin):
    if has_frontend_tool_failure(output):
        return False
    nuxt_exit_codes = re.findall(
        r'(?m)^\s*ERROR\s+Process exited with non-zero status \((\d+)\)\s*$',
        output,
    )
    if nuxt_exit_codes != ['2']:
        return False
    diagnostics = [
        list(match.groups())
        for match in re.finditer(
            r'^(.+?)\(\d+,\d+\): error (TS\d+): (.*)$', output, re.M
        )
    ]
    additional = Counter(map(tuple, diagnostics)) - Counter(map(tuple, baseline['diagnostics']))
    return baseline['pin'] == pin and bool(diagnostics) and not additional


def resolve_pnpm_launcher(toolchain_root, platform=None):
    pnpm = toolchain_root/'pnpm/node_modules/.bin/pnpm'
    if (platform or os.name) == 'nt':
        pnpm_cmd = pnpm.with_suffix('.cmd')
        if pnpm_cmd.exists():
            return pnpm_cmd
    return pnpm


def brand_frontend():
    # Brand values and assets change; API identifiers, theme keys and URLs stay native.
    for folder in ('pages', 'components', 'layouts'):
        for path in (BUILD/folder).rglob('*.vue'):
            text = re.sub(r'\bHome(?:Box|box)\b', 'C-Crate', path.read_text())
            path.write_text(text)
    for path in (BUILD/'nuxt.config.ts', BUILD/'lib/data/themes.ts'):
        text = path.read_text().replace('"Homebox"', '"C-Crate"').replace('"Home Inventory App"', '"Workshop inventory and equipment checkout"')
        path.write_text(text)
    def values(value):
        if isinstance(value, str): return value.replace('HomeBox', 'C-Crate').replace('Homebox', 'C-Crate')
        if isinstance(value, dict): return {key: values(item) for key, item in value.items()}
        if isinstance(value, list): return [values(item) for item in value]
        return value
    for path in (BUILD/'locales').glob('*.json'):
        path.write_text(json.dumps(values(json.loads(path.read_text(encoding='utf-8'))), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    logo = (ROOT/'kiosk/branding/caci-create.svg').read_text()
    (BUILD/'components/App/Logo.vue').write_text('<template>\n'+logo+'</template>\n')
    shutil.copytree(ROOT/'kiosk/branding', BUILD/'public', dirs_exist_ok=True)
    replace('pages/index.vue', '            HomeB\n            <AppLogo class="-mb-4 w-12" />\n            x', '<AppLogo aria-hidden="true" class="mr-3 size-14 shrink-0" /><span>C-Crate</span>')
    replace('layouts/default.vue', '          </NuxtLink>\n\n          <CollectionSelector />', '            <span class="block text-center text-base font-bold group-data-[collapsible=icon]:hidden">C-Crate</span>\n          </NuxtLink>\n\n          <CollectionSelector />')


def item_log_frontend():
    # One fail-closed template anchor keeps the disclosure beside native Details.
    path = 'pages/item/[id]/index.vue'
    replace(path, '  import LabelMaker from', '  import WorkshopItemLog from "@/components/Workshop/ItemLog.vue";\n  import ItemLoans from "@/components/Workshop/ItemLoans.vue";\n  import LabelMaker from')
    details_anchor = '          </DetailsSection>\n        </BaseCard>\n\n        <!-- anything in this is not rendered if on another page -->'
    replace(path, details_anchor, '          </DetailsSection>\n          <div v-if="item.displayId" class="flex items-center gap-2 px-6 pb-2"><span class="text-sm text-muted-foreground" title="Generated from item type and full storage path; regenerated when the item moves.">Display ID</span><code class="font-mono font-semibold">{{ item.displayId }}</code><CopyText :text="item.displayId" :icon-size="16" /></div>\n          <div v-if="item.shortCode" class="flex items-center gap-2 px-6 pb-4"><span class="text-sm text-muted-foreground">Short code</span><code class="font-mono font-semibold">{{ item.shortCode }}</code><CopyText :text="item.shortCode" :icon-size="16" /></div>\n        </BaseCard>\n\n        <WorkshopItemLog v-if="!hasNested" :item-id="itemId" />\n\n        <!-- anything in this is not rendered if on another page -->')


def item_metadata_detail_frontend():
    path = 'pages/item/[id]/index.vue'
    replace(path, '  import LabelMaker from', '  import ItemMetadataPanel from "@/components/Workshop/ItemMetadataPanel.vue";\n  import LabelMaker from')
    replace(path, '<WorkshopItemLog v-if="!hasNested" :item-id="itemId" />', '<ItemMetadataPanel v-if="!hasNested && item" :item="item" @changed="refresh" />\n        <WorkshopItemLog v-if="!hasNested" :item-id="itemId" />')


def equipment_assigned_ids_frontend():
    """Project collection-assigned IDs into search and detail views."""
    def once(path, old, new):
        target = BUILD/path
        text = target.read_text()
        if text.count(old) != 1:
            raise RuntimeError(f'Upstream changed: expected one equipment ID patch anchor in {path}')
        target.write_text(text.replace(old, new))

    once('pages/items.vue', '  import type { LocationQueryRaw } from "vue-router";',
         '  import type { LocationQueryRaw } from "vue-router";\n  import { fetchAssignedDisplayIds, projectAssignedDisplayIds, resolveAssignedIdAfterNativeMiss } from "@/lib/equipment-search.js";\n  import { matchInventoryCustomFields } from "@/lib/child-item-groups.js";')
    once('pages/items.vue', '  const api = useUserApi();', '  const api = useUserApi();\n  const equipmentWorkshop = useWorkshop();\n  let searchRevision = 0;')
    once('pages/items.vue', '''  async function search() {
    if (searchLocked.value) {
      return;
    }

    loading.value = true;''', '''  async function search() {
    if (searchLocked.value) {
      return;
    }
    const revision = ++searchRevision;
    const searchedQuery = query.value;

    loading.value = true;''')
    once('pages/items.vue', '      q: query.value || "",', '      q: searchedQuery || "",')
    once('pages/items.vue', '''      fields,
    });

    function resetItems()''', '''      fields,
    });
    if (revision !== searchRevision || searchedQuery !== query.value) return;

    function resetItems()''')
    once('pages/items.vue', '''    if (!data.items || data.items.length === 0) {
      resetItems();
      return;
    }''', '''    if (!data.items || data.items.length === 0) {
      const resolvedId = await resolveAssignedIdAfterNativeMiss(searchedQuery, data.items || [], (displayId: string) =>
        equipmentWorkshop.request("equipment/ids/resolve", { display_id: displayId }),
        () => revision === searchRevision && searchedQuery === query.value
      );
      if (revision !== searchRevision || searchedQuery !== query.value) return;
      if (resolvedId) {
        loading.value = false;
        await navigateTo(`/item/${resolvedId}`);
        return;
      }
      resetItems();
      return;
    }''')
    once('pages/items.vue', '    total.value = data.total;\n    items.value = data.items;', '''    let assignmentMap = {};
    try {
      assignmentMap = await fetchAssignedDisplayIds(data.items.map(item => item.id), ids =>
        equipmentWorkshop.request(`equipment/ids?entity_ids=${encodeURIComponent(ids.join(","))}`)
      );
    } catch { /* Keep native IDs if the optional catalog lookup is unavailable. */ }
    if (revision !== searchRevision || searchedQuery !== query.value) return;
    total.value = data.total;
    items.value = projectAssignedDisplayIds(data.items, assignmentMap);''')

    once('pages/items.vue', '  watchDebounced([page, pageSize, query, selectedTags, selectedLocations], search, { debounce: 250, maxWait: 1000 });', '''  watch([page, pageSize, query, selectedTags, selectedLocations], () => { searchRevision++; }, { flush: "sync" });
  watchDebounced([page, pageSize, query, selectedTags, selectedLocations], search, { debounce: 250, maxWait: 1000 });''')

    once('pages/item/[id]/index.vue', '  const api = useUserApi();', '  const api = useUserApi();\n  const equipmentWorkshop = useWorkshop();\n  const assignedDisplayId = ref("");')
    data_anchor = '''  const { data: item, refresh } = useAsyncData(itemId.value, async () => {
    const { data, error } = await api.items.get(itemId.value);
    if (error) {
      toast.error(t("items.toast.failed_load_item"));
      navigateTo("/home");
      return;
    }
    return data;
  });'''
    once('pages/item/[id]/index.vue', data_anchor, data_anchor + '''
  const effectiveDisplayId = computed(() => assignedDisplayId.value || item.value?.displayId || "");
  watch(itemId, async id => {
    assignedDisplayId.value = "";
    try {
      const assignments = await equipmentWorkshop.request<Record<string, { display_id: string }>>(
        `equipment/ids?entity_ids=${encodeURIComponent(id)}`
      );
      if (itemId.value === id) assignedDisplayId.value = assignments[id]?.display_id || "";
    } catch { /* Keep the native ID if the optional catalog lookup is unavailable. */ }
  }, { immediate: true });''')
    detail_line = '          <div v-if="item.displayId" class="flex items-center gap-2 px-6 pb-2"><span class="text-sm text-muted-foreground" title="Generated from item type and full storage path; regenerated when the item moves.">Display ID</span><code class="font-mono font-semibold">{{ item.displayId }}</code><CopyText :text="item.displayId" :icon-size="16" /></div>'
    once('pages/item/[id]/index.vue', detail_line, '          <div v-if="effectiveDisplayId" class="flex items-center gap-2 px-6 pb-2"><span class="text-sm text-muted-foreground">{{ assignedDisplayId ? "Equipment ID" : "Display ID" }}</span><code class="font-mono font-semibold">{{ effectiveDisplayId }}</code><CopyText :text="effectiveDisplayId" :icon-size="16" /></div>')

    once('components/Item/View/table/columns.ts', '    {\n      id: "name",', '''    {
      id: "displayId",
      accessorKey: "displayId",
      header: () => h("span", { class: "text-sm font-medium" }, "Equipment ID"),
      cell: ({ row }) => h("code", { class: "font-mono text-sm" }, String(row.getValue("displayId") ?? "")),
    },
    {
      id: "name",''')
    once('components/Item/View/table/columns.ts', '      id: "displayId",', '''      id: "thumbnail",
      accessorKey: "thumbnailUrl",
      header: () => h("span", { class: "text-sm font-medium" }, "Photo"),
      cell: ({ row }) => {
        const src = String((row.original as any).thumbnailUrl || "");
        return src ? h("img", { src, alt: "", class: "size-10 rounded object-cover" }) : h("span", { class: "text-xs text-muted-foreground" }, "No photo");
      },
    },
    {
      id: "equipmentStatus",
      accessorKey: "equipmentStatus",
      header: () => h("span", { class: "text-sm font-medium" }, "Status"),
      cell: ({ row }) => h("span", { class: "text-sm" }, String(row.getValue("equipmentStatus") || "Unknown")),
    },
    {
      id: "displayId",''')
    once('components/Item/View/table/data-table.vue', 'const defaultVisible = ["name", "quantity", "insured", "purchasePrice"];', 'const defaultVisible = ["displayId", "thumbnail", "equipmentStatus", "location", "name"];')


def move_create_actions_after_photo_preview(source):
    """Keep both existing create actions after uploaded-photo previews."""
    action_open = '      <div class="mt-4 flex flex-row-reverse">'
    action_start = source.find(action_open)
    preview_start = source.find('      <PhotoUploaderPreview\n')
    if action_start < 0 or preview_start < 0:
        raise RuntimeError('Upstream changed: expected the create actions and photo preview in CreateModal.vue')
    if source.count(action_open) != 1 or source.count('      <PhotoUploaderPreview\n') != 1:
        raise RuntimeError('Upstream changed: expected one create action block and photo preview in CreateModal.vue')

    action_close = source.find('\n      </div>', action_start)
    button_group_start = source.find('        <ButtonGroup>', action_start, action_close)
    if action_close < 0 or button_group_start < 0:
        raise RuntimeError('Upstream changed: expected the create buttons inside their actions block')
    button_group_end = source.find('        </ButtonGroup>', button_group_start)
    if button_group_end < 0 or button_group_end > action_close:
        raise RuntimeError('Upstream changed: expected the create buttons inside their actions block')
    if source[action_start + len(action_open):button_group_start].strip() or source[button_group_end + len('        </ButtonGroup>'):action_close].strip():
        raise RuntimeError('Upstream changed: expected only the create button group inside its actions block')
    action_end = action_close + len('\n      </div>')
    actions = source[action_start:action_end]
    if actions.count('type="submit"') != 1 or actions.count('@click="create(false)"') != 1:
        raise RuntimeError('Upstream changed: expected both existing create actions in CreateModal.vue')
    if preview_start < action_start:
        return source

    if source[action_end:preview_start] != '\n\n':
        raise RuntimeError('Upstream changed: expected create actions directly before the photo preview')
    preview_tag_end = source.find('>', preview_start)
    if preview_tag_end < 0 or source[preview_tag_end - 1] != '/':
        raise RuntimeError('Upstream changed: expected a self-closing photo preview in CreateModal.vue')
    preview_end = preview_tag_end + 1
    return source[:action_start] + '\n\n' + source[preview_start:preview_end] + '\n\n' + actions + source[preview_end:]


def grouped_inventory_frontend():
    """Render collection filtered inventory as cross-location product groups."""
    once = lambda old, new: replace('pages/items.vue', old, new)
    once('  import type { LocationQueryRaw } from "vue-router";',
         '  import type { LocationQueryRaw } from "vue-router";\n  import { loadAllFilteredInventory, loadInventoryActionStatuses, groupInventoryItems, buildInventoryStoragePath, mergeInventorySummaries, inventoryNoteRequestKey, createInventoryNoteVersionGuard } from "@/lib/child-item-groups.js";\n  import { recentItemNotes } from "@/lib/item-activity-notes.js";')
    once('  const items = ref<EntitySummary[]>([]);\n  const total = ref(0);',
         '  const items = ref<EntitySummary[]>([]);\n  const inventoryGroups = ref<any[]>([]);\n  const nativeManagePage = ref(1);\n  const nativeTotal = ref(0);\n  const nativeManageItems = computed(() => items.value.slice((nativeManagePage.value - 1) * pageSize.value, nativeManagePage.value * pageSize.value));\n  const total = ref(0);')
    once('  const inventoryGroups = ref<any[]>([]);\n  const nativeManagePage = ref(1);', '  const inventoryGroups = ref<any[]>([]);\n  const recentInventoryNotes = ref<Record<string, any>>({});\n  const noteLoadingGroups = ref(new Set<string>());\n  const noteLoadedGroups = ref(new Set<string>());\n  const noteRequestVersions = createInventoryNoteVersionGuard();\n  const noteLoadVersions = new Map<string, number>();\n  let inventoryNotesIdentity = "";\n  const nativeManagePage = ref(1);')
    once('''    const searchedQuery = query.value;

    loading.value = true;''', '''    const searchedQuery = query.value;
    const currentIdentity = equipmentWorkshop.context.value?.identity || "";
    if (inventoryNotesIdentity !== currentIdentity) {
      inventoryNotesIdentity = currentIdentity;
      recentInventoryNotes.value = {};
      noteLoadingGroups.value = new Set();
      noteLoadedGroups.value = new Set();
    }

    loading.value = true;''')
    once('''  const pagination = proxyRefs({
    page,
    pageSize,
    totalSize: total,
    setPage: (newPage: number) => {
      page.value = newPage;
    },
  });''', '''  const pagination = proxyRefs({
    page,
    pageSize,
    totalSize: total,
    setPage: (newPage: number) => { page.value = newPage; },
  });
  const nativePagination = proxyRefs({
    page: nativeManagePage,
    pageSize,
    totalSize: nativeTotal,
    setPage: (newPage: number) => { nativeManagePage.value = newPage; },
  });
  async function loadInventoryNotes(request: { key: string; entityIds: string[]; refresh?: boolean }) {
    const noteKey = inventoryNoteRequestKey(request.key, request.entityIds);
    if ((!request.refresh && noteLoadedGroups.value.has(noteKey)) || (noteLoadingGroups.value.has(noteKey) && !request.refresh)) return;
    const requestIdentity = equipmentWorkshop.context.value?.identity || "";
    const entityVersions = noteRequestVersions.begin(request.entityIds);
    const loadVersion = (noteLoadVersions.get(noteKey) || 0) + 1;
    noteLoadVersions.set(noteKey, loadVersion);
    noteLoadingGroups.value = new Set(noteLoadingGroups.value).add(noteKey);
    try {
      const found = new Map<string, any[]>();
      let cursor = 0;
      const workers = Array.from({ length: Math.min(4, request.entityIds.length) }, async () => {
        while (cursor < request.entityIds.length) {
          const entityId = request.entityIds[cursor++]!;
          found.set(entityId, await equipmentWorkshop.request<any[]>("history?entity=" + encodeURIComponent(entityId)));
        }
      });
      await Promise.all(workers);
      if (requestIdentity !== (equipmentWorkshop.context.value?.identity || "") || requestIdentity !== inventoryNotesIdentity) return;
      const notes = { ...recentInventoryNotes.value };
      for (const entityId of request.entityIds) {
        if (noteRequestVersions.isCurrent(entityVersions, entityId)) notes[entityId] = recentItemNotes(found.get(entityId) || [], entityId, 1)[0] || null;
      }
      recentInventoryNotes.value = notes;
      if (request.entityIds.every(entityId => noteRequestVersions.isCurrent(entityVersions, entityId))) noteLoadedGroups.value = new Set(noteLoadedGroups.value).add(noteKey);
    } catch { /* The unit row remains usable when optional return history is unavailable. */ }
    finally {
      if (requestIdentity === inventoryNotesIdentity && loadVersion === noteLoadVersions.get(noteKey)) {
        const next = new Set(noteLoadingGroups.value); next.delete(noteKey); noteLoadingGroups.value = next;
      }
    }
  }''')
    old = '''    const { data, error } = await api.items.getAll({
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
    });'''
    new = '''    const nativeOptions = {
      q: "",
      parentIds: locIDs.value,
      tags: tagIDs.value,
      negateTags: negateTags.value,
      onlyWithoutPhoto: onlyWithoutPhoto.value,
      onlyWithPhoto: onlyWithPhoto.value,
      includeArchived: includeArchived.value,
      pageSize: pageSize.value,
      orderBy: orderBy.value,
      fields,
    };
    let data: any = null;
    let nativeMatches: any[] = [];
    let error: any = null;
    try {
      const allItems = await loadAllFilteredInventory(async (nativePage: number, nativePageSize: number) => {
        const response = await api.items.getAll({ ...nativeOptions, page: nativePage, pageSize: nativePageSize });
        if (response.error) throw response.error;
        return response.data;
      }, { pageSize: pageSize.value, isCurrent: () => revision === searchRevision && searchedQuery === query.value });
      nativeMatches = searchedQuery.trim() ? await loadAllFilteredInventory(async (nativePage: number, nativePageSize: number) => {
        const response = await api.items.getAll({ ...nativeOptions, q: searchedQuery, page: nativePage, pageSize: nativePageSize });
        if (response.error) throw response.error;
        return response.data;
      }, { pageSize: pageSize.value, isCurrent: () => revision === searchRevision && searchedQuery === query.value }) : allItems;
      data = { items: allItems, total: allItems.length };
    } catch (loadError) { error = loadError; }'''
    once(old, new)
    once('''    if (error) {
      resetItems();
      toast.error(t("items.toast.failed_search_items"));
      return;
    }''', '''    if (error) {
      // A failed page must not replace a previously complete inventory with partial or zero totals.
      loading.value = false;
      toast.error(t("items.toast.failed_search_items"));
      return;
    }''')
    once('      total.value = 0;\n      items.value = [];', '      total.value = 0;\n      items.value = [];\n      inventoryGroups.value = [];')
    old_project = '''    let assignmentMap = {};
    try {
      assignmentMap = await fetchAssignedDisplayIds(data.items.map(item => item.id), ids =>
        equipmentWorkshop.request(`equipment/ids?entity_ids=${encodeURIComponent(ids.join(","))}`)
      );
    } catch { /* Keep native IDs if the optional catalog lookup is unavailable. */ }
    if (revision !== searchRevision || searchedQuery !== query.value) return;
    total.value = data.total;
    items.value = projectAssignedDisplayIds(data.items, assignmentMap);'''
    new_project = '''    let assignmentMap: Record<string, any> = {};
    let statuses: Record<string, any> = {};
    let locationRows: any[] = [];
    let equipmentRows: any[] = [];
    try {
      assignmentMap = await fetchAssignedDisplayIds(data.items.map((item: any) => item.id), (ids: string[]) =>
        equipmentWorkshop.request(`equipment/ids?entity_ids=${encodeURIComponent(ids.join(","))}`)
      );
    } catch { /* Native rows remain visible with their native IDs. */ }
    try {
      const [fullRows, locations] = await Promise.all([equipmentWorkshop.request<any[]>("equipment"), equipmentWorkshop.request<any[]>("locations")]);
      equipmentRows = fullRows || [];
      locationRows = locations || [];
    } catch { /* Missing authoritative status stays unknown. */ }
    if (revision !== searchRevision || searchedQuery !== query.value) return;
    try {
      statuses = await loadInventoryActionStatuses(equipmentRows.map((row: any) => row.id), (ids: string[]) =>
        equipmentWorkshop.request(`item-actions/status?ids=${encodeURIComponent(ids.join(","))}`),
        { isCurrent: () => revision === searchRevision && searchedQuery === query.value && currentIdentity === (equipmentWorkshop.context.value?.identity || "") }
      );
    } catch { /* Missing authoritative status stays unknown. */ }
    if (revision !== searchRevision || searchedQuery !== query.value) return;
    const enriched = mergeInventorySummaries(data.items, equipmentRows);
    const projected = projectAssignedDisplayIds(enriched, assignmentMap);
    const matchingEntityIds = new Set(nativeMatches.map(item => item.id));
    const normalizedQuery = searchedQuery.trim().toLocaleLowerCase();
    if (normalizedQuery) for (const item of projected) {
      if (String(item.displayId || "").toLocaleLowerCase().includes(normalizedQuery)) matchingEntityIds.add(item.id);
    }
    if (normalizedQuery) for (const item of matchInventoryCustomFields(projected, searchedQuery)) matchingEntityIds.add(item.id);
    const managementMatches = projected.filter((item: any) => matchingEntityIds.has(item.id));
    const locationById = [...equipmentRows, ...locationRows];
    const storagePath = (item: any) => buildInventoryStoragePath(item, locationById);
    let templateThumbnails: Record<string, any> = {};
    try {
      const templates = await equipmentWorkshop.request<any[]>("equipment/templates");
      for (const template of templates || []) {
        if (template.product_id && template.photo_entity_id && template.photo_attachment_id) templateThumbnails[template.product_id] = { entity_id: template.photo_entity_id, attachment_id: template.photo_attachment_id };
      }
    } catch { /* Native item photos remain primary; missing templates are optional. */ }
    if (revision !== searchRevision || searchedQuery !== query.value) return;
    inventoryGroups.value = groupInventoryItems(projected, assignmentMap, { query: searchedQuery, matchedEntityIds: [...matchingEntityIds], statuses, storagePath, templateThumbnails, recentNotes: recentInventoryNotes.value });
    page.value = Math.min(page.value, Math.max(1, Math.ceil(inventoryGroups.value.length / pageSize.value)));
    total.value = inventoryGroups.value.length;
    items.value = data.items;'''
    once(old_project, new_project)
    once('''    total.value = inventoryGroups.value.length;
    items.value = data.items;''', '''    total.value = inventoryGroups.value.length;
    nativeTotal.value = managementMatches.length;
    nativeManagePage.value = Math.min(nativeManagePage.value, Math.max(1, Math.ceil(managementMatches.length / pageSize.value)));
    items.value = managementMatches.map((item: any) => {
      const status = (statuses as Record<string, any>)[item.id]?.status || (statuses as Record<string, any>)[item.id]?.availability || "unknown";
      const photoId = item.thumbnailId || item.imageId;
      return { ...item, displayId: assignmentMap[item.id]?.display_id || item.displayId || "", equipmentStatus: status === "unknown" ? "Unknown" : status.replaceAll("_", " "), thumbnailUrl: photoId ? api.authURL(`/entities/${item.id}/attachments/${photoId}`) : "" };
    });''')
    once('''      <ItemViewSelectable
        :items="items"
        :location-flat-tree="locationFlatTree"
        :pagination="pagination"
        disable-sort
        @refresh="async () => search()"
      />''', '''      <InventoryGroups :groups="inventoryGroups" :page="page" :page-size="pageSize" :recent-notes="recentInventoryNotes" :note-loading-keys="[...noteLoadingGroups]" :note-loaded-keys="[...noteLoadedGroups]" @load-notes="loadInventoryNotes" @refresh-items="search" @update:page="(value: number) => { page = value; }" />
      <details v-if="items.length" class="mt-4 rounded-lg border p-3">
        <summary class="cursor-pointer font-medium">Manage matching native items</summary>
        <ItemViewSelectable :items="nativeManageItems" :location-flat-tree="locationFlatTree" :pagination="nativePagination" disable-sort @refresh="async () => search()" />
      </details>''')


def item_action_surfaces_frontend():
    """Mount one shared action host and add exact-item triggers to native rows."""
    def once(path, old, new):
        target = BUILD / path
        source = target.read_text()
        if source.count(old) != 1:
            raise RuntimeError(f'Upstream changed: expected one item-action mount anchor in {path}')
        target.write_text(source.replace(old, new))

    once('layouts/default.vue', '<script lang="ts" setup>', '<script lang="ts" setup>\n  import ItemActionHost from "~/components/Workshop/ItemActionHost.vue";')
    once('layouts/default.vue', '    <ModalConfirm />', '    <ModalConfirm />\n    <ItemActionHost />')
    once('components/Item/View/table/table-view.vue', '  import DataTableExpandedRow from "./data-table-expanded-row.vue";', '  import DataTableExpandedRow from "./data-table-expanded-row.vue";\n  import ItemQuickActions from "~/components/Workshop/ItemQuickActions.vue";')
    once('components/Item/View/table/table-view.vue', '<FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />', '<FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />\n              <ItemQuickActions v-if="cell.column.id === \'actions\'" :item-id="row.original.id" compact />')
    once('components/Item/View/table/card-view.vue', '  import DropdownAction from "./data-table-dropdown.vue";', '  import DropdownAction from "./data-table-dropdown.vue";\n  import ItemQuickActions from "~/components/Workshop/ItemQuickActions.vue";')
    once('components/Item/View/table/card-view.vue', '''    <ItemCard
      v-for="item in table.getRowModel().rows"
      :key="item.original.id"
      :item="item.original"
      :table-row="preferences.quickActions.enabled ? item : undefined"
      :location-flat-tree="locationFlatTree"
    />''', '''    <div v-for="item in table.getRowModel().rows" :key="item.original.id" class="space-y-2">
      <ItemCard
        :item="item.original"
        :table-row="preferences.quickActions.enabled ? item : undefined"
        :location-flat-tree="locationFlatTree"
      />
      <ItemQuickActions :item-id="item.original.id" compact />
    </div>''')


def nest_frontend():
    replace('lib/api/classes/items.ts', '  orderBy?: string;', '  orderBy?: string;\n  isLocation?: boolean;')
    replace(
        'components/ui/dialog-provider/utils.ts',
        '  [DialogID.CreateEntity]:\n    | { baseType: "item"; product?: BarcodeProduct; barcode?: string; subItem?: true; resume?: true }\n    | { baseType: "location" };',
        '  [DialogID.CreateEntity]: (\n    | { baseType: "item"; product?: BarcodeProduct; barcode?: string; subItem?: true; resume?: true }\n    | { baseType: "location" }\n  ) & { parentId?: string };',
    )
    path = 'components/Entity/CreateModal.vue'
    replace(path, ':entity-types="subItemCreate ? entityTypes.filter(t => !t.isLocation) : entityTypes"', ':entity-types="entityTypes"')
    target = BUILD/path
    source = target.read_text()
    # Older frontend pins did not yet include model-number handling. Add it
    # only when absent; barcode-aware pins already supply the complete flow.
    if 'v-model="form.modelNumber"' not in source:
        replace(path, '      <FormTextField\n        v-if="!selectedEntityType?.isLocation"\n        v-model.number="form.quantity"', '      <FormTextField v-if="!selectedEntityType?.isLocation" v-model="form.modelNumber" label="Model number" :max-length="255" />\n      <FormTextField\n        v-if="!selectedEntityType?.isLocation"\n        v-model.number="form.quantity"')
    elif source.count('v-model="form.modelNumber"') != 1:
        raise RuntimeError(f'Upstream changed: expected one model-number control in {path}')
    if 'modelNumber: "",' not in source:
        replace(path, '    name: "",\n    quantity: 1,', '    name: "",\n    modelNumber: "",\n    quantity: 1,')
    elif source.count('modelNumber: "",') != 1:
        raise RuntimeError(f'Upstream changed: expected one model-number form field in {path}')
    if 'form.modelNumber = "";' not in source:
        replace(path, '    form.name = "";\n    form.quantity = 1;', '    form.name = "";\n    form.modelNumber = "";\n    form.quantity = 1;')
    target = BUILD/path
    text = target.read_text()
    selector = '      <ItemSelector\n'
    if text.count(selector) != 1:
        raise RuntimeError(f'Upstream changed: expected one sub-item selector in {path}')
    start = text.index(selector)
    end = text.index('\n      />', start) + len('\n      />')
    text = text[:start]+text[end:]
    import_block = text[text.index('  import type {'):text.index('  } from "~~/lib/api/types/data-contracts";')]
    if 'EntitySummary,' not in import_block:
        if text.count('    EntityCreate,') != 1:
            raise RuntimeError(f'Upstream changed: expected one EntityCreate import in {path}')
        text = text.replace('    EntityCreate,', '    EntityCreate,\n    EntitySummary,')
    elif import_block.count('EntitySummary,') != 1:
        raise RuntimeError(f'Upstream changed: expected one EntitySummary import in {path}')
    text = text.replace('const found = locations.value.find(l => l.id === data.defaultLocation!.id);', 'const { data: found } = await api.items.get(data.defaultLocation.id);')
    text = text.replace('location: locations.value && locations.value.length > 0 ? locations.value[0] : ({} as EntityOut)', 'location: null as EntitySummary | null')
    text = text.replace('      form.parentId = null;', '      form.parentId = null;\n      form.location = null;')
    text = text.replace('            parent.value = data;', '            parentItemLocationId = data.id;')
    start = text.index('          if (data.parent) {'); end = text.index('\n        }', start)
    text = text[:start]+text[end:]
    location_context_anchor = '''      const locId = locationId.value ? locationId.value : parentItemLocationId;
      applyInitialBarcodeParamAfterContext(initialBarcode, form, lookupBarcode, () => {
        if (locId) {
          const found = locations.value.find(l => l.id === locId);
          if (found) {
            form.location = found;
          }
        }

        if (tagId.value) {'''
    if text.count(location_context_anchor) != 1:
        raise RuntimeError(f'Upstream changed: expected one barcode-aware location context anchor in {path}')
    text = text.replace(
        location_context_anchor,
        '''      const locId = params.parentId || locationId.value || parentItemLocationId;
      if (locId) {
        const { data } = await api.items.get(String(locId));
        if (data) form.location = data;
      }

      applyInitialBarcodeParamAfterContext(initialBarcode, form, lookupBarcode, () => {
        if (tagId.value) {''',
    )
    start = text.index('    // Items must live somewhere'); end = text.index('    if (loading.value)', start)
    text = text[:start]+text[end:]
    text = text.replace('parentId: form.location.id as string', 'parentId: form.location?.id || null').replace('parentId: form.parentId || (form.location.id as string)', 'parentId: form.location?.id || null')
    # Barcode-aware upstream already owns the model-number field, state and
    # create payloads. Keep the overlay from reinserting duplicate keys/imports.
    existing_model_number_payloads = text.count('modelNumber: form.modelNumber,')
    if existing_model_number_payloads not in (0, 3):
        raise RuntimeError(f'Upstream changed: expected zero or three model-number payloads in {path}')
    if existing_model_number_payloads == 0:
        if text.count('const templateRequest = {') != 1:
            raise RuntimeError(f'Upstream changed: expected one template request in {path}')
        text = text.replace('const templateRequest = {', 'const templateRequest = {\n        modelNumber: form.modelNumber?.trim() || undefined,')
        payload_anchor = '        name: form.name,\n        quantity: form.quantity,\n        description: form.description,'
        if text.count(payload_anchor) != 1:
            raise RuntimeError(f'Upstream changed: expected one normal item payload in {path}')
        text = text.replace(payload_anchor, '        name: form.name,\n        modelNumber: form.modelNumber?.trim() || undefined,\n        quantity: form.quantity,\n        description: form.description,')
    import_block = text[text.index('  import type {'):text.index('  } from "~~/lib/api/types/data-contracts";')]
    form_block = text[text.index('  const form = reactive({'):text.index('\n  });', text.index('  const form = reactive({'))]
    if import_block.count('EntitySummary,') != 1 or form_block.count('modelNumber: "",') != 1:
        raise RuntimeError(f'Upstream changed: expected one EntitySummary import and modelNumber form field in {path}')
    if text.count('modelNumber: form.modelNumber,') != 3:
        raise RuntimeError(f'Upstream changed: expected modelNumber in each native create payload in {path}')
    text = move_create_actions_after_photo_preview(text)
    target.write_text(text)
    path = 'pages/item/[id]/index/edit.vue'; target=BUILD/path; text=target.read_text()
    start=text.index('    if (data.parent && data.parent.entityType'); end=text.index('\n    return data;',start)
    text=text[:start]+text[end:]
    guard='''    if (!item.value.parent?.id && !parent.value?.id) {
      toast.error(t("items.toast.failed_save_no_location"));
      return;
    }
'''
    assert text.count(guard)==2; text=text.replace(guard,'')
    text=text.replace('parent.value?.id || item.value.parent?.id || null','item.value.parent?.id || null')
    text=text.replace('<LocationSelector v-model="item.parent" @update:model-value="informAboutDesyncingLocationFromParent()" />','<LocationSelector v-model="item.parent" :current-location="item" />')
    start=text.index('            <ItemSelector\n'); end=text.index('            <TagSelector',start)
    text=text[:start]+'            <p class="text-sm text-muted-foreground">Contents stay inside this item when it moves.</p>\n'+text[end:]
    start=text.index('  async function maybeSyncWithParentLocation()');end=text.index('  onMounted(() => {',start)
    text=text[:start]+text[end:]
    text=text.replace('  const { query, results, isLoading, triggerSearch } = useItemSearch(api, { immediate: false });\n  const parent = ref();\n','')
    target.write_text(text)
    replace('pages/location/[id]/index/edit.vue', '<LocationSelector v-model="parent" label="Parent Location" :current-location="item" />', '<LocationSelector v-model="parent" :current-location="item" />')
    for path, model in [('pages/item/[id]/index.vue','item'),('pages/location/[id]/index/index.vue','location')]:
        replace(path, '  import LabelMaker from', '  import InsideActions from "@/components/Workshop/InsideActions.vue";\n  import LabelMaker from')
        replace(path, '            <div class="ml-auto mt-2 flex flex-wrap items-center justify-between gap-2">', '            <div class="ml-auto mt-2 flex flex-wrap items-center justify-between gap-2">\n              <InsideActions :entity-id="'+model+'.id" :archived="'+model+'.archived" />')
    replace('pages/item/[id]/index.vue', '  import ItemViewSelectable from', '  import LocationCard from "@/components/Location/Card.vue";\n  import ItemViewSelectable from')
    replace('pages/item/[id]/index.vue', '<section v-if="items && items.length > 0" class="mt-6">', '<section v-if="item?.children?.length || (items && items.length > 0)" class="mt-6">')
    replace('pages/item/[id]/index.vue', '      <ItemViewSelectable :items="items" @refresh="refreshItemList" />', '''      <section v-if="item?.children?.length" class="mt-6">
        <h2 class="mb-3 text-xl font-semibold">Locations inside</h2>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-3"><LocationCard v-for="child in item.children" :key="child.id" :location="child" /></div>
      </section>
      <ItemViewSelectable v-if="items && items.length" :items="items || []" @refresh="refreshItemList" />''')

    path='lib/api/types/data-contracts.ts';target=BUILD/path;text=target.read_text();text=text.replace('export interface EntitySummary {','export interface EntitySummary {\n  displayId: string;\n  shortCode: string;').replace('export interface EntityOut {','export interface EntityOut {\n  displayId: string;\n  shortCode: string;').replace('export interface EntityPatch {','export interface EntityPatch {\n  clearParent?: boolean;')
    for interface_name in ('EntityCreate', 'EntityTemplateCreateItemRequest'):
        start = text.index(f'export interface {interface_name} {{')
        end = text.index('\n}', start)
        if 'modelNumber?: string;' not in text[start:end]:
            text = text[:start] + text[start:end].replace('{', '{\n  modelNumber?: string;', 1) + text[end:]
    start=text.index('export interface EntityTemplateCreateItemRequest {');end=text.index('\n}',start)
    text=text[:start]+text[start:end].replace('parentId: string;','parentId: string | null;')+text[end:];target.write_text(text)
    replace('composables/use-barcode-detector.ts','api.items.getAll({ locations: [id] })','api.items.getAll({ parentIds: [id] })')
    path='components/Item/View/ItemChangeDetails.vue';target=BUILD/path;text=target.read_text()
    text=text.replace('item.location','item.parent').replace(']!.location',']!.parent')
    text=text.replace('      items.value = params.items;', '      items.value = params.items;\n      newLocation.value = null;')
    text=text.replace('!items.value.length || (enabled.changeLocation && !location)', '!items.value.length')
    text=text.replace('patch.parentId = location!.id;', 'if (location) patch.parentId = location.id; else patch.clearParent = true;')
    text=text.replace('v-model="newLocation" />','v-model="newLocation" :exclude-ids="items.map(item => item.id)" />')
    text=text.replace('saving || (enabled.changeLocation && !newLocation)','saving')
    target.write_text(text)
    path='components/Location/Tree/tree-state.ts';target=BUILD/path;text=target.read_text()
    text+='\nexport function containsLocation(node: import("@/lib/api/types/data-contracts").TreeItem): boolean { const todo = [node]; while (todo.length) { const current = todo.pop()!; if (current.type === "location") return true; todo.push(...(current.children || [])); } return false; }\n';target.write_text(text)
    replace('components/Location/Tree/Node.vue','import { useTreeState }','import { useTreeState, containsLocation }')
    replace('components/Location/Tree/Node.vue','children.filter(child => child.type === "location")','children.filter(containsLocation)')
    replace('components/Location/Tree/Root.vue','  import type { TreeItem }','  import { containsLocation } from "./tree-state";\n  import type { TreeItem }')
    replace('components/Location/Tree/Root.vue','const list = props.locs ?? [];','const list = (props.locs ?? []).filter(node => props.showItems !== false || containsLocation(node));')
    replace('pages/locations.vue','@click="openAll"','@click="openAll" :aria-label="$t(\'locations.expand_tree\')"')
    replace('pages/locations.vue','@click="closeAll"','@click="closeAll" :aria-label="$t(\'locations.collapse_tree\')"')
    replace('pages/locations.vue','@click="showItems = !showItems"','@click="showItems = !showItems" :aria-label="showItems ? $t(\'locations.hide_items\') : $t(\'locations.show_items\')"')
    # Mixed ancestors link to their actual native item/location pages.
    path='pages/location/[id]/index/index.vue'
    target=BUILD/path; text=target.read_text()
    text=text.replace('  const confirm = useConfirm();', '  const fullpath = computedAsync(async () => location.value ? (await api.items.fullpath(location.value.id)).data || [] : []);\n\n  const confirm = useConfirm();')
    start=text.index('              <Breadcrumb v-if="location?.parent">');end=text.index('              </Breadcrumb>',start)+len('              </Breadcrumb>')
    text=text[:start]+'''              <Breadcrumb v-if="fullpath && fullpath.length > 1">
                <BreadcrumbList><template v-for="(part, idx) in fullpath" :key="part.id">
                  <BreadcrumbItem><BreadcrumbLink v-if="idx < fullpath.length - 1" as-child><NuxtLink :to="`/${part.type}/${part.id}`">{{ part.name }}</NuxtLink></BreadcrumbLink><span v-else>{{ part.name }}</span></BreadcrumbItem>
                  <BreadcrumbSeparator v-if="idx < fullpath.length - 1" />
                </template></BreadcrumbList>
              </Breadcrumb>'''+text[end:]
    target.write_text(text)


def navigation_frontend():
    replace('layouts/default.vue', '      <Sidebar collapsible="icon">', '      <Sidebar side="left" collapsible="icon">')
    replace('layouts/default.vue', '<Collapsible v-else default-open', '<Collapsible v-else :default-open="n.name.value !== \'More\'"')
    replace('layouts/default.vue', '<SidebarMenuLink\n                        :href="n.to"', '<CollapsibleTrigger v-if="n.name.value === \'More\'" as-child><SidebarMenuButton :tooltip="n.name.value" class="flex gap-2"><component :is="n.icon" /><span>{{ n.name.value }}</span><MdiChevronRight class="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" /></SidebarMenuButton></CollapsibleTrigger>\n                      <SidebarMenuLink v-else\n                        :href="n.to"')
    replace('layouts/default.vue', '<CollapsibleTrigger as-child>\n                        <SidebarMenuButton class="flex size-12', '<CollapsibleTrigger v-if="n.name.value !== \'More\'" as-child>\n                        <SidebarMenuButton class="flex size-12')
    replace('layouts/default.vue', '    collapsible?: {\n      active: ComputedRef<boolean>;', '    collapsible?: {\n      action?: () => void;\n      active: ComputedRef<boolean>;')
    replace('layouts/default.vue', '<SidebarMenuLink\n                            :href="c.to"', '<SidebarMenuLink v-if="!c.action"\n                            :href="c.to"')
    replace('layouts/default.vue', '                          </SidebarMenuLink>\n                        </SidebarMenuSubItem>', '                          </SidebarMenuLink>\n                          <SidebarMenuButton v-else @click.prevent="c.action?.()"><span>{{ c.name.value }}</span></SidebarMenuButton>\n                        </SidebarMenuSubItem>')


    layout = BUILD/'layouts/default.vue'
    source = layout.read_text()
    start = source.index('              <!-- makes scanner accessible easily if using legacy header -->')
    end = source.index('              </SidebarMenuItem>', start) + len('              </SidebarMenuItem>\n')
    layout.write_text(source[:start] + source[end:])
    replace('layouts/default.vue', 'const nav: {', 'const baseNav: {')
    replace('layouts/default.vue', '  const quickMenuActions = reactive([', '''  const workshop = useWorkshop();
  const { selectedId: workshopGroup } = useCollections();
  const workshopLinks = computed(() => [
    ["loans", "Loans & notes"], ["map", "Workshop & storage"], ["equipment-ids", "Equipment ID codes"],
    ["checkout-cart", "Checkout cart"],
    ...(workshop.manager.value ? [["imports", "Imports"], ["labels", "Label queue"], ["recovery", "Recovery"], ["system", "System"]] : []),
  ]);
  const nav = computed<typeof baseNav>(() => [
    baseNav[0]!,
    { ...baseNav[3]!, id: 1, name: computed(() => "Inventory") },
    { id: 8, icon: MdiWrench, name: computed(() => "Workshop"), to: "/workshop/map", active: computed(() => route.path === "/workshop/map") },
    { ...baseNav[1]!, id: 12 },
    { id: 9, icon: MdiTagMultiple, name: computed(() => "Label"), to: "/workshop/labels", active: computed(() => route.path === "/workshop/labels") },
    { ...baseNav[7]!, id: 10, name: computed(() => "Users"), to: "/collection/members", active: computed(() => route.path === "/collection/members"), collapsible: undefined },
    {
      id: 11, icon: MdiFileDocumentMultiple, name: computed(() => "More"), to: "",
      active: computed(() => false),
      collapsible: [
        baseNav[2]!, baseNav[4]!, baseNav[5]!, baseNav[6]!,
        ...baseNav[7]!.collapsible!.filter(item => item.to !== "/collection/members"),
        ...workshopLinks.value.filter(([id]) => id !== "map" && id !== "labels").map(([id, name], index) => ({ id: 80 + index, name: computed(() => name!), to: `/workshop/${id}`, active: computed(() => route.path === `/workshop/${id}`) })),
        { id: 92, name: computed(() => "Report feedback"), to: "/feedback", active: computed(() => route.path === "/feedback") },
        { id: 90, name: computed(() => "Equipment Terminal"), to: terminalURL.value, active: computed(() => false) },
        { id: 91, name: computed(() => t("menu.scanner")), to: "", active: computed(() => false), action: openScanner },
      ],
    },
  ]);
  watch([workshopGroup, () => useAuthContext().user?.id], () => { workshop.context.value = null; workshop.refresh().catch(() => {}); }, { immediate: true });

  const quickMenuActions = computed(() => [''')
    replace('layouts/default.vue', '...nav.map(v => ({', '...nav.value.filter(v => v.name.value !== "More").map(v => ({')
    target = BUILD/'layouts/default.vue'
    target.write_text(target.read_text().replace('text: computed(() => v.name.value),', 'text: v.name.value,'))


def location_child_contents_frontend():
    # The common ChildContents root already owns grouped rows, hydration,
    # filtering and refresh. Mount it for direct items on every location page;
    # keep native bulk actions available behind an explicit disclosure.
    replace(
        'pages/location/[id]/index/index.vue',
        '  import ItemViewSelectable from "~/components/Item/View/Selectable.vue";',
        '  import ItemViewSelectable from "~/components/Item/View/Selectable.vue";\n  import ChildContents from "~/components/Location/ChildContents.vue";',
    )
    replace(
        'pages/location/[id]/index/index.vue',
        '''      <!-- Items in this location -->
      <section v-if="location && items">
        <ItemViewSelectable :items="items" @refresh="refreshItemList" />
      </section>''',
        '''      <!-- Grouped direct contents use the same view on root bins and leaves. -->
      <ChildContents v-if="location" :key="`${location.id}-${contentsRevision}`" :locations="[location]" direct-only heading="Items in this location" />
      <details v-if="items?.length" :key="`manage-${locationId}`" class="mt-3 rounded-lg border p-3">
        <summary class="cursor-pointer font-medium">Manage items</summary>
        <ItemViewSelectable class="mt-3" :items="items" @refresh="async () => { contentsRevision++; await refreshItemList(); }" />
      </details>''',
    )
    replace(
        'pages/location/[id]/index/index.vue',
        '''      <!-- Child locations -->
      <section v-if="location && location.children && location.children.length > 0" class="mt-6">
        <BaseSectionHeader class="mb-5"> {{ $t("locations.child_locations") }} </BaseSectionHeader>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <LocationCard v-for="child in location.children" :key="child.id" :location="child" />
        </div>
      </section>''',
        '''      <!-- Expandable, read-only previews for child locations -->
      <ChildContents v-if="location && location.children?.length" :key="`children-${location.id}-${contentsRevision}`" :locations="location.children" />''',
    )
    replace(
        'pages/location/[id]/index/index.vue',
        '  const locationId = computed<string>(() => route.params.id as string);',
        '  const locationId = computed<string>(() => route.params.id as string);\n  const contentsRevision = ref(0);',
    )
    replace(
        'pages/location/[id]/index/index.vue',
        'useAsyncData(locationId.value, async () => {',
        'useAsyncData(() => locationId.value, async () => {',
    )


def shell_frontend():
    layout = BUILD/'layouts/default.vue'
    source = layout.read_text()
    start = source.index('<SidebarHeader class="items-center">')
    selector = '          <CollectionSelector />'
    end = source.index(selector, start) + len(selector)
    source = source[:start] + '''<SidebarHeader class="items-stretch gap-2 p-3">
          <NuxtLink to="/home" aria-label="C-Crate home" class="flex h-10 w-full items-center gap-3 rounded-md px-2 text-sidebar-foreground hover:bg-sidebar-accent group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
            <AppLogo aria-hidden="true" class="size-7 shrink-0" />
          </NuxtLink>

          <CollectionSelector />'''+source[end:]
    layout.write_text(source)
    replace('layouts/default.vue', '    SidebarGroupLabel,\n', '')
    replace('layouts/default.vue', 'drop-shadow-md hover:bg-primary/90', 'hover:bg-primary/90')
    replace('layouts/default.vue', 'class="flex justify-center group-data-[collapsible=icon]:justify-start group-data-[collapsible=icon]:bg-destructive group-data-[collapsible=icon]:text-destructive-foreground group-data-[collapsible=icon]:shadow-sm group-data-[collapsible=icon]:hover:bg-destructive/90"', 'class="flex justify-center rounded-md text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground group-data-[collapsible=icon]:justify-start"')
    replace('layouts/default.vue', 'class="sticky top-0 z-20 flex h-[var(--header-height-mobile)] translate-y-[-0.5px] flex-col bg-secondary p-2 shadow-md sm:h-[var(--header-height)] sm:flex-row"', 'class="sticky top-0 z-20 flex min-h-[var(--header-height-mobile)] flex-col gap-1 border-b border-border bg-card px-3 py-2 sm:min-h-[var(--header-height)] sm:flex-row"')
    replace('layouts/default.vue', '            <div class="flex h-1/2 grow items-center justify-end gap-2 sm:h-auto">', '            <div class="ccrate-header-tools flex min-w-0 grow flex-wrap items-center justify-end gap-2">\n              <DeviceStatus v-if="!preferences.displayLegacyHeader || !terminalHeader" :enabled="!preferences.displayLegacyHeader || !terminalHeader" class="ccrate-header-device shrink-0" />')
    replace('layouts/default.vue', '              <SidebarTrigger variant="default" />', '              <SidebarTrigger class="ccrate-header-sidebar-trigger" variant="default" />')
    replace('layouts/default.vue', '        <AppHeaderDecor class="-mt-10 hidden lg:block" />', '''        <AppHeaderDecor class="-mt-10 hidden lg:block" />
            <DeviceStatus v-if="preferences.displayLegacyHeader && terminalHeader" :enabled="preferences.displayLegacyHeader && terminalHeader" class="ccrate-header-device absolute right-6 top-3 z-30 hidden lg:flex" />''')
    replace('layouts/default.vue', '<SidebarTrigger class="absolute left-2 top-2 hidden lg:flex" variant="default" />', '<SidebarTrigger class="ccrate-header-sidebar-trigger absolute left-2 top-2 hidden lg:flex" variant="default" />')
    replace('layouts/default.vue', '<Button size="icon" @click="triggerSearch">', '<Button size="icon" :aria-label="$t(\'global.search\')" @click="triggerSearch">')
    replace('layouts/default.vue', '<Button size="icon" @click="openScanner">', '<Button size="icon" :aria-label="$t(\'menu.scanner\')" @click="openScanner">')
    replace('layouts/default.vue', '              <Input\n                v-model:model-value="search"', '              <div class="ccrate-header-search-group">\n                <Input\n                v-model:model-value="search"')
    replace('layouts/default.vue', '<MdiQrcodeScan />\n                </Button>\n              </div>\n            </div>', '<MdiQrcodeScan />\n                </Button>\n              </div>\n              </div>\n            </div>')
    replace('layouts/default.vue', '  const search = ref("");', '''  const terminalHeader = ref(false);
  let desktopHeaderMedia: MediaQueryList | null = null;
  const updateDesktopHeader = () => { terminalHeader.value = desktopHeaderMedia?.matches || false; };
  onMounted(() => { desktopHeaderMedia = window.matchMedia("(min-width: 1024px)"); updateDesktopHeader(); desktopHeaderMedia.addEventListener("change", updateDesktopHeader); });
  onBeforeUnmount(() => desktopHeaderMedia?.removeEventListener("change", updateDesktopHeader));
  const terminalURL = computed(() => { const url = new URL(window.location.href); url.port = "17749"; url.pathname = "/"; url.search = "?mode=editor"; url.hash = ""; return url.href; });
  const search = ref("");''')
    replace('layouts/default.vue', '  import AppHeaderDecor from "~/components/App/HeaderDecor.vue";', '  import DeviceStatus from "~/components/Workshop/DeviceStatus.vue";\n  import AppHeaderDecor from "~/components/App/HeaderDecor.vue";')


def ocr_popover_frontend():
    regular = '<DeviceStatus v-if="!preferences.displayLegacyHeader || !terminalHeader" :enabled="!preferences.displayLegacyHeader || !terminalHeader" class="ccrate-header-device shrink-0" />'
    replace('layouts/default.vue', regular, regular + '\n              <div id="orc-launcher-toolbar" class="contents"></div>')
    legacy = '<SidebarTrigger class="ccrate-header-sidebar-trigger absolute left-2 top-2 hidden lg:flex" variant="default" />'
    replace('layouts/default.vue', legacy, legacy + '\n            <div id="orc-launcher-legacy" class="absolute left-14 top-2 z-30 hidden lg:flex"></div>')
    replace('layouts/default.vue', '      </SidebarInset>', '        <OcrPopover :launcher-target="orcLauncherTarget" />\n      </SidebarInset>')
    replace('layouts/default.vue', '  const search = ref("");', '  const { activeDialog: orcActiveDialog } = useDialog();\n  const orcLauncherTarget = ref("#orc-launcher-toolbar");\n  watch([orcActiveDialog, () => preferences.value.displayLegacyHeader, terminalHeader], async () => { await new Promise<void>(resolve => setTimeout(resolve, 0)); orcLauncherTarget.value = orcActiveDialog.value === DialogID.CreateEntity ? "#orc-launcher-create" : preferences.value.displayLegacyHeader && terminalHeader.value ? "#orc-launcher-legacy" : "#orc-launcher-toolbar"; }, { immediate: true, flush: "post" });\n  const search = ref("");')
    replace('layouts/default.vue', '  import AppHeaderDecor from "~/components/App/HeaderDecor.vue";', '  import OcrPopover from "~/components/Workshop/OcrPopover.vue";\n  import AppHeaderDecor from "~/components/App/HeaderDecor.vue";')


def strip_item_response_short_codes_from_update_tests():
    """Keep response-only identifiers out of update payloads in pinned API tests."""
    relative = pathlib.Path('lib/api/__test__/user/items.test.ts')
    target = BUILD / relative
    source = target.read_text()
    if not re.search(r'\b(?:displayId|shortCode)\b', source):
        return
    rewrites = (
        ("    const itemUpdate = {\n      ...item,\n      entityTypeId: item.entityType?.id || \"\",\n      parentId: item.parent?.id || null,", "    const { displayId: omittedItemDisplayID, shortCode: omittedItemShortCode, ...itemForUpdate } = item;\n    void omittedItemDisplayID;\n    void omittedItemShortCode;\n    const itemUpdate = {\n      ...itemForUpdate,\n      entityTypeId: item.entityType?.id || \"\",\n      parentId: item.parent?.id || null,"),
        ("    const child1ItemUpdate = {\n      ...child1Item,\n      entityTypeId: child1Item.entityType?.id || \"\",\n      parentId: parent.id,", "    const { displayId: omittedChild1DisplayID, shortCode: omittedChild1ShortCode, ...child1ForUpdate } = child1Item;\n    void omittedChild1DisplayID;\n    void omittedChild1ShortCode;\n    const child1ItemUpdate = {\n      ...child1ForUpdate,\n      entityTypeId: child1Item.entityType?.id || \"\",\n      parentId: parent.id,"),
        ("    const child2ItemUpdate = {\n      ...child2Item,\n      entityTypeId: child2Item.entityType?.id || \"\",\n      parentId: parent.id,", "    const { displayId: omittedChild2DisplayID, shortCode: omittedChild2ShortCode, ...child2ForUpdate } = child2Item;\n    void omittedChild2DisplayID;\n    void omittedChild2ShortCode;\n    const child2ItemUpdate = {\n      ...child2ForUpdate,\n      entityTypeId: child2Item.entityType?.id || \"\",\n      parentId: parent.id,"),
        ("    const itemUpdate = {\n      ...parent,\n      entityTypeId: parent.entityType?.id || \"\",\n      parentId: parentLocation.id,", "    const { displayId: omittedParentDisplayID, shortCode: omittedParentShortCode, ...parentForUpdate } = parent;\n    void omittedParentDisplayID;\n    void omittedParentShortCode;\n    const itemUpdate = {\n      ...parentForUpdate,\n      entityTypeId: parent.entityType?.id || \"\",\n      parentId: parentLocation.id,"),
    )
    if len(rewrites) != 4:
        raise RuntimeError('Expected four pinned item update test fixtures')
    for original, replacement in rewrites:
        count = source.count(original)
        if count == 0 and source.count(replacement) == 1:
            continue
        if count != 1:
            raise RuntimeError(f'Expected exactly one item update fixture anchor in {relative}, found {count}')
        source = source.replace(original, replacement)
    target.write_text(source)


def camera_ocr_frontend():
    path = 'pages/item/[id]/index/edit.vue'
    replace(
        path,
        '  import { recognizeNameFromFileLocally } from "~/components/Form/camera";',
        '  import { recognizeNameFromImage, suggestNameWithoutOverwritingEdits } from "~/lib/local-ocr";',
    )
    replace(
        path,
        '''  async function suggestItemNameFromPhoto(file: File) {
    try {
      const suggestion = await recognizeNameFromFileLocally(file);
      if (!suggestion) {
        nameOcrMessage.value = t("components.form.camera.name_not_found");
        return;
      }
      item.value.name = suggestion;
      nameOcrMessage.value = t("components.form.camera.name_suggested");
    } catch {
      nameOcrMessage.value = t("components.form.camera.name_unavailable");
    }
  }''',
        '''  async function suggestItemNameFromPhoto(file: File) {
    try {
      nameOcrMessage.value = t("components.form.camera.ocr_running");
      const outcome = await suggestNameWithoutOverwritingEdits({
        getName: () => item.value.name,
        getRevision: () => nameEditRevision.value,
        setName: (value: string) => { item.value.name = value; },
        recognize: recognizeNameFromImage,
        image: file,
      });
      if (outcome === "empty") {
        nameOcrMessage.value = t("components.form.camera.name_not_found");
      } else if (outcome === "edited-during-recognition") {
        nameOcrMessage.value = t("components.form.camera.name_preserved");
      } else {
        nameOcrMessage.value = t("components.form.camera.name_suggested");
      }
    } catch {
      nameOcrMessage.value = t("components.form.camera.name_unavailable");
    }
  }''',
    )
    replace(path, '  const nameOcrMessage = ref("");', '  const nameOcrMessage = ref("");\n  const nameEditRevision = ref(0);')
    replace(
        path,
        '                    v-model="item[field.ref]"\n                    class="min-w-0 flex-1"',
        '                    v-model="item[field.ref]"\n                    @update:model-value="nameEditRevision++"\n                    class="min-w-0 flex-1"',
    )
    replace(
        path,
        '''                  </Button>
                </div>
                <FormTextField
                  v-else-if="field.type === 'text'"''',
        '''                  </Button>
                </div>
                <p v-if="field.ref === 'name'" class="mt-1 text-xs text-muted-foreground">
                  {{ $t("components.form.camera.local_ocr_notice") }}
                </p>
                <FormTextField
                  v-else-if="field.type === 'text'"''',
    )

    modal = 'components/Entity/CreateModal.vue'
    replace(
        modal,
        '  import { recognizeNameFromFileLocally } from "~/components/Form/camera";',
        '  import { recognizeNameFromImage, suggestNameWithoutOverwritingEdits } from "~/lib/local-ocr";',
    )
    replace(
        modal,
        '  const { openDialog, closeDialog, registerOpenDialogCallback } = useDialog();',
        '  const { activeDialog, openDialog, closeDialog, registerOpenDialogCallback } = useDialog();',
    )
    replace(
        modal,
        '  const nameOcrMessage = ref("");',
        '  const nameOcrMessage = ref("");\n  const nameEditRevision = ref(0);\n  let nameOcrGeneration = 0;\n  watch(activeDialog, value => { if (value !== DialogID.CreateEntity) { nameOcrGeneration++; nameOcrMessage.value = ""; } }, { flush: "sync" });',
    )
    replace(
        modal,
        '''  async function suggestNameFromPhoto(file: File) {
    try {
      const suggestion = await recognizeNameFromFileLocally(file);
      if (!suggestion) {
        nameOcrMessage.value = t("components.form.camera.name_not_found");
        return;
      }
      form.name = suggestion;
      nameOcrMessage.value = t("components.form.camera.name_suggested");
    } catch {
      nameOcrMessage.value = t("components.form.camera.name_unavailable");
    }
  }''',
        '''  async function suggestNameFromPhoto(file: File) {
    const request = ++nameOcrGeneration;
    try {
      nameOcrMessage.value = t("components.form.camera.ocr_running");
      const outcome = await suggestNameWithoutOverwritingEdits({
        getName: () => form.name,
        getRevision: () => nameEditRevision.value,
        setName: (value: string) => { form.name = value; },
        recognize: recognizeNameFromImage,
        isCurrent: () => request === nameOcrGeneration,
        image: file,
      });
      if (outcome === "stale") return;
      if (outcome === "empty") {
        nameOcrMessage.value = t("components.form.camera.name_not_found");
      } else if (outcome === "edited-during-recognition") {
        nameOcrMessage.value = t("components.form.camera.name_preserved");
      } else {
        nameOcrMessage.value = t("components.form.camera.name_suggested");
      }
    } catch {
      if (request !== nameOcrGeneration) return;
      nameOcrMessage.value = t("components.form.camera.name_unavailable");
    }
  }''',
    )
    replace(modal, '    form.name = "";', '    nameOcrGeneration++;\n    nameOcrMessage.value = "";\n    form.name = "";')
    replace(
        modal,
        '          v-model="form.name"\n          class="min-w-0 flex-1"',
        '          v-model="form.name"\n          @update:model-value="nameEditRevision++"\n          class="min-w-0 flex-1"',
    )
    replace(
        modal,
        '      <p v-if="nameOcrMessage" class="text-sm text-muted-foreground" role="status">{{ nameOcrMessage }}</p>',
        '      <p v-if="nameOcrMessage" class="text-sm text-muted-foreground" role="status">{{ nameOcrMessage }}</p>\n      <p class="text-xs text-muted-foreground">{{ $t("components.form.camera.local_ocr_notice") }}</p>',
    )
    locale = BUILD/'locales/en.json'
    data = json.loads(locale.read_text(encoding='utf-8'))
    camera = data['components']['form']['camera']
    camera['name_preserved'] = 'Your typed name was kept. OCR finished in the background.'
    camera['ocr_running'] = 'Reading the label in this browser… first use may download OCR code and the English model.'
    camera['local_ocr_notice'] = 'Name suggestions run in this browser, and the suggestion photo is not uploaded. OCR code and the English model download on first use.'
    locale.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


import re

def smart_create_form_text(text):
    def once(old, new):
        nonlocal text
        if text.count(old) != 1: raise RuntimeError(f'Smart create anchor changed: {old[:80]}')
        text = text.replace(old, new)
    # Drop all native and equipment template entry points, retaining their APIs and data.
    text, count = re.subn(r'          <!-- Template selector button -->.*?\n\s*<ButtonGroup>', '          <ButtonGroup>', text, count=1, flags=re.S)
    if count != 1: raise RuntimeError('Template selector markup changed')
    text, count = re.subn(r'      <!-- Template Info Display - Collapsible banner.*?\n      </div>\n\n', '', text, count=1, flags=re.S)
    if count != 1: raise RuntimeError('Template banner markup changed')
    text, count = re.subn(r'      <EquipmentTemplatePanel.*?\n      />\n', '', text, count=1, flags=re.S)
    if count != 1: raise RuntimeError('Equipment template panel changed')
    text, count = re.subn(r'    } else if \(templateData.value\) \{.*?\n    } else \{\n      // Normal item creation without template', '    } else {\n      // Normal item creation without template', text, count=1, flags=re.S)
    if count != 1: raise RuntimeError('Native template create branch changed')
    once('  import { workshopUUID } from "~/lib/workshop-uuid";\n  import { applyEquipmentTemplateDefaults, assignCreatedEquipment, confirmNoMainCreate, createEquipmentCreationFlow, equipmentTemplateStorageKey } from "~/lib/equipment-catalog";\n  import EquipmentTemplatePanel from "~/components/Workshop/EquipmentTemplatePanel.vue";',
         '  import { workshopUUID } from "~/lib/workshop-uuid";\n  import { assignCreatedEquipment, confirmNoMainCreate, createEquipmentCreationFlow, equipmentTemplateStorageKey } from "~/lib/equipment-catalog";\n  import { PACKAGING_OPTIONS, createSuggestionLookup, selectSuggestion, validateCustomRows, buildNativeMetadataUpdate, nativeMetadataMatches, persistFieldNotes } from "~/lib/item-create-fields";')
    once('  import TemplateSelector from "~/components/Template/Selector.vue";\n', '')
    once('    EntityTemplateOut,\n    EntityTemplateSummary,\n', '')
    once('  import MdiFileDocumentOutline from "~icons/mdi/file-document-outline";\n  import MdiChevronDown from "~icons/mdi/chevron-down";\n  import MdiClose from "~icons/mdi/close";\n', '')
    once('  const equipmentTemplateId = ref<string | null>(null);\n', '')
    text = text.replace('    equipmentTemplateId.value = null;\n', '')
    text, count = re.subn(r'  function applyEquipmentTemplate\(template: any\) \{.*?\n  }\n', '', text, count=1, flags=re.S)
    if count != 1: raise RuntimeError('Template apply function changed')
    start=text.index('  async function onEntityTypeChanged(typeId: string) {')
    end=text.index('  const loading = ref(false);', start)
    text=text[:start]+'''  function onEntityTypeChanged(typeId: string) {
    selectedEntityType.value = entityTypes.value.find(t => t.id === typeId) || null;
    suggestionSearchVersion++;
    suggestionLookup.invalidate();
    suggestions.value = [];
  }

'''+text[end:]
    start=text.index('  const selectedTemplate = ref<')
    end=text.index('  const form = reactive({', start)
    text=text[:start]+text[end:]
    start=text.index('  async function handleTemplateSelected(')
    end=text.index('  watch(\n    parent,',start)
    text=text[:start]+text[end:]
    once('        // Restore last used template if available\n        await restoreLastTemplate();\n', '')
    once('      if (!equipmentTemplateId.value && !form.modelCode.trim()) {\n        toast.error("Enter an equipment model code or choose a saved template.");',
         '      if (!form.modelCode.trim()) {\n        toast.error("Enter an equipment model code.");')
    once('          templateId: equipmentTemplateId.value || undefined,\n', '')
    once('    selectedTemplate.value = null;\n    templateData.value = null;\n    templateUserSelected.value = false;\n    showTemplateDetails.value = false;\n', '')
    once('    () => [selectedEntityType.value?.id, selectedTemplate.value?.id, templateData.value?.id, parent.value?.id, subItemCreate.value],',
         '    () => [selectedEntityType.value?.id, parent.value?.id, subItemCreate.value],')
    once('        selectedTemplateId: selectedTemplate.value?.id,\n        templateId: templateData.value?.id,\n', '')
    # Retain standalone OCR popover; remove photo-to-name camera controls from this form.
    start=text.index('        <Button type="button" variant="outline" @click="nameCameraOpen = true">')
    end=text.index('      <FormTextField\n        v-if="!selectedEntityType?.isLocation"',start)
    text=text[:start]+'''      </div>
      <div id="orc-launcher-create" class="min-h-10"></div>
      <div v-if="suggestions.length" class="rounded-md border p-2" role="listbox" aria-label="Similar items">
        <button v-for="(item, index) in suggestions" :key="item.id" type="button" role="option" :aria-selected="index === suggestionIndex" class="block w-full rounded p-2 text-left hover:bg-accent" @click="chooseSuggestion(item)">
          {{ item.name }} · {{ item.manufacturer }} {{ item.modelNumber }}
        </button>
      </div>
'''+text[end:]
    once('          @update:model-value="nameEditRevision++"', '          @update:model-value="searchSuggestions"\n          @keydown.down.prevent="moveSuggestion(1)"\n          @keydown.up.prevent="moveSuggestion(-1)"\n          @keydown.enter="chooseHighlightedSuggestion"\n          @keydown.esc="suggestions = []"')
    once('    <CameraCaptureDialog v-model:open="nameCameraOpen" @captured="suggestNameFromPhoto" />\n', '')
    once('  import CameraCaptureDialog from "~/components/Form/CameraCaptureDialog.vue";\n  import { recognizeNameFromImage, suggestNameWithoutOverwritingEdits } from "~/lib/local-ocr";\n', '')
    start=text.index('  const nameCameraOpen = ref(false);')
    end=text.index('  // Entity type selection',start)
    text=text[:start]+text[end:]
    start=text.index('  async function suggestNameFromPhoto(')
    # OCR helper appears later; remove its exact function by balanced braces.
    depth=0; close=None
    for index in range(start,len(text)):
        if text[index]=='{': depth+=1
        elif text[index]=='}':
            depth-=1
            if depth==0: close=index+1; break
    text=text[:start]+text[close:]
    once('    nameOcrGeneration++;\n    nameOcrMessage.value = "";\n', '')
    once('    modelCode: "",', '    modelCode: "",\n    serialNumber: "",\n    packaging: "",\n    customRows: [] as Array<{ name: string; value: string; note: string }>,')
    once('        <FormTextField v-model="form.modelCode" label="Equipment model code" :max-length="80" />', '''        <FormTextField v-model="form.modelCode" label="Equipment model code" :max-length="80" />
        <FormTextField v-model="form.serialNumber" label="Manufacturer serial number" :max-length="255" />''')
    once('      <section v-if="equipmentIntent"', '''      <div v-if="!selectedEntityType?.isLocation" class="space-y-2">
        <label for="device-packaging">Device Packaging</label>
        <select id="device-packaging" v-model="form.packaging" class="w-full rounded-md border bg-background p-2">
          <option value="">Unknown</option>
          <option v-for="option in PACKAGING_OPTIONS" :key="option" :value="option">{{ option }}</option>
        </select>
        <table class="w-full"><thead><tr><th>Name</th><th>Value</th><th>Note</th><th></th></tr></thead><tbody>
          <tr v-for="(row, index) in form.customRows" :key="index">
            <td><input v-model="row.name" aria-label="Custom field name" class="w-full rounded border p-1" /></td>
            <td><input v-model="row.value" aria-label="Custom field value" class="w-full rounded border p-1" /></td>
            <td><input v-model="row.note" aria-label="Custom field note" class="w-full rounded border p-1" /></td>
            <td><Button type="button" variant="ghost" @click="form.customRows.splice(index, 1)">Remove</Button></td>
          </tr>
        </tbody></table>
        <Button type="button" variant="outline" @click="form.customRows.push({ name: '', value: '', note: '' })">Add field</Button>
      </div>
      <section v-if="equipmentIntent"''')
    once('  const equipmentWorkshop = useWorkshop();', '''  const equipmentWorkshop = useWorkshop();
  const suggestions = ref<any[]>([]);
  const suggestionIndex = ref(0);
  let suggestionSearchVersion = 0;
  const suggestionLookup = createSuggestionLookup((typeId: string, query: string) => equipmentWorkshop.request(`equipment/suggestions?type_id=${encodeURIComponent(typeId)}&q=${encodeURIComponent(query)}`));
  async function searchSuggestions() {
    const typeId = selectedEntityType.value?.isLocation ? '' : selectedEntityType.value?.id || '';
    const version = ++suggestionSearchVersion;
    try { const found = await suggestionLookup.search(typeId, form.name); if (version === suggestionSearchVersion) { suggestions.value = found; suggestionIndex.value = 0; } }
    catch { if (version === suggestionSearchVersion) suggestions.value = []; }
  }
  function moveSuggestion(delta: number) { if (suggestions.value.length) suggestionIndex.value = (suggestionIndex.value + delta + suggestions.value.length) % suggestions.value.length; }
  function chooseSuggestion(item: any) { suggestionSearchVersion++; suggestionLookup.invalidate(); selectSuggestion(form, item); suggestions.value = []; }
  function chooseHighlightedSuggestion(event: KeyboardEvent) { if (suggestions.value.length) { event.preventDefault(); chooseSuggestion(suggestions.value[suggestionIndex.value]); } }''')
    once('          postCreateSteps: form.photos.map((photo: PhotoPreview, index: number) => ({', '''          postCreateSteps: [
            { key: 'metadata', name: 'Native item fields', draft: { serialNumber: form.serialNumber, packaging: form.packaging, rows: validateCustomRows(form.customRows) } },
            { key: 'field-notes', name: 'Custom field notes', request_key: workshopUUID(), fields: validateCustomRows(form.customRows).map(row => ({ name: row.name, note: row.note.trim() })) },
            ...form.photos.map((photo: PhotoPreview, index: number) => ({''')
    once('            name: photo.photoName, size: photo.file.size, last_modified: photo.file.lastModified, primary: photo.primary,\n          })),',
         '            name: photo.photoName, size: photo.file.size, last_modified: photo.file.lastModified, primary: photo.primary,\n          })),\n          ],')
    once('          const photo = form.photos.find(', '''          if (step.key === 'metadata') {
            const before = await api.items.get(intent.entity_id);
            if (before.error || !before.data) return { error: before.error || new Error('Could not read the native item.') };
            if (nativeMetadataMatches(before.data, step.draft)) return {};
            const payload = buildNativeMetadataUpdate(before.data, step.draft);
            const updated = await api.items.update(intent.entity_id, payload);
            if (updated.error) return updated;
            const after = await api.items.get(intent.entity_id);
            if (after.error || !after.data || !nativeMetadataMatches(after.data, step.draft)) return { error: new Error('Homebox did not confirm item fields.') };
            return {};
          }
          if (step.key === 'field-notes') {
            await persistFieldNotes(equipmentWorkshop, intent, step);
            return {};
          }
          const photo = form.photos.find(''')
    once('    form.modelCode = "";\n', '    form.modelCode = "";\n    form.serialNumber = "";\n    form.packaging = "";\n    form.customRows = [];\n    suggestions.value = [];\n')
    return related_create_form_text(text)

def remove_equipment_template_navigation():
    replace('layouts/default.vue', '''    {
      icon: MdiFileDocumentMultiple,
      id: 4,
      active: computed(() => route.path === "/templates"),
      name: computed(() => t("menu.templates")),
      to: "/templates",
    },
''', '')

def related_create_form_text(text):
    def once(old, new):
        nonlocal text
        if text.count(old) != 1: raise RuntimeError(f'Related create anchor changed: {old[:80]}')
        text = text.replace(old, new)
    once('  import { PACKAGING_OPTIONS, createSuggestionLookup, selectSuggestion, validateCustomRows, buildNativeMetadataUpdate, nativeMetadataMatches, persistFieldNotes } from "~/lib/item-create-fields";',
         '  import { PACKAGING_OPTIONS, createSuggestionLookup, selectSuggestion, validateCustomRows, buildNativeMetadataUpdate, nativeMetadataMatches, persistFieldNotes } from "~/lib/item-create-fields";\n  import { createRelatedItemFlow, relatedItemStorageKey } from "~/lib/item-metadata";')
    once('  const equipmentWorkshop = useWorkshop();', '''  const equipmentWorkshop = useWorkshop();
  const stagedRelated = ref<Array<{ name: string; entityTypeId: string; parentId: string; description: string; manufacturer: string; modelNumber: string }>>([]);
  const relatedIntent = ref<any>(null);
  const relatedReconcileIds = ref<Record<string, string>>({});
  let relatedFlow: ReturnType<typeof createRelatedItemFlow> | null = null;
  let relatedFlowKey = "";
  async function getRelatedFlow() {
    const context = await equipmentWorkshop.refresh();
    const key = relatedItemStorageKey(context);
    if (!relatedFlow || relatedFlowKey !== key) {
      const read = () => { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; } };
      relatedFlow = createRelatedItemFlow({
        read, write: (value: any) => value ? localStorage.setItem(key, JSON.stringify(value)) : localStorage.removeItem(key),
        expectedContext: context, context: () => equipmentWorkshop.refresh(),
        keyFactory: workshopUUID,
        createNative: (item: any) => api.items.create(item),
        link: (main: string, related: string, requestKey: string) => equipmentWorkshop.request('item-metadata/related/add', { request_key: requestKey, entity_id: main, related_entity_id: related }, context.identity),
        readLinks: (main: string) => equipmentWorkshop.request(`item-metadata?entity_id=${encodeURIComponent(main)}`),
      });
      relatedFlowKey = key;
    }
    if (relatedFlow.pending()?.steps.every((step: any) => step.state === 'completed')) relatedFlow.clearCompleted();
    relatedIntent.value = relatedFlow.pending();
    return relatedFlow;
  }
  function addStagedRelated() {
    stagedRelated.value.push({ name: "", entityTypeId: selectedEntityType.value?.id || "", parentId: form.location?.id || "", description: "", manufacturer: "", modelNumber: "" });
  }
  async function retryRelated(stepKey: string) {
    try { const flow = await getRelatedFlow(); await flow.retryRelatedStep(stepKey); relatedIntent.value = flow.pending(); }
    catch (error) { relatedIntent.value = relatedFlow?.pending(); toast.error((error as Error).message); }
  }
  async function reconcileRelated(stepKey: string) {
    const id = relatedReconcileIds.value[stepKey]?.trim();
    if (!id) return;
    try {
      const flow = await getRelatedFlow();
      const step = flow.pending()?.steps.find((row: any) => row.key === stepKey);
      const result = await api.items.get(id);
      if (result.error || !result.data || result.data.id !== id || result.data.entityType?.id !== step?.item?.entityTypeId) throw new Error('This UUID is not the staged related item in this collection.');
      flow.reconcileRelatedCreate(stepKey, id);
      relatedIntent.value = flow.pending();
      delete relatedReconcileIds.value[stepKey];
    } catch (error) { toast.error((error as Error).message); }
  }
  async function confirmRelatedAbsent(stepKey: string) {
    try { const flow = await getRelatedFlow(); flow.confirmRelatedCreateAbsent(stepKey); relatedIntent.value = flow.pending(); }
    catch (error) { toast.error((error as Error).message); }
  }
  async function resumeRelated() {
    try { const flow = await getRelatedFlow(); await flow.resumeRelatedSteps(); relatedIntent.value = flow.pending(); }
    catch (error) { relatedIntent.value = relatedFlow?.pending(); toast.error((error as Error).message); }
  }''')
    once('    equipmentFlowContext = null;\n    equipmentIntent.value = null;',
         '    equipmentFlowContext = null;\n    equipmentIntent.value = null;\n    relatedFlow = null; relatedFlowKey = ""; relatedIntent.value = null;\n    if (activeDialog.value === DialogID.CreateEntity) void getRelatedFlow();')
    once('      equipmentIntent.value = flow.reconcileCreated(id);',
         '      equipmentIntent.value = flow.reconcileCreated(id);\n      const related = await getRelatedFlow();\n      if (related.pending()?.steps.length) { related.recordMainCreated(id); relatedIntent.value = related.pending(); }')
    once('        equipmentCreateFlow = await getEquipmentFlow();\n        equipmentCreateFlow.begin({',
         '''        equipmentCreateFlow = await getEquipmentFlow();
        const related = await getRelatedFlow();
        if (related.pending()?.steps.length) throw new Error('Resolve the pending related items before another main create.');
        for (const row of stagedRelated.value) {
          related.stageRelated({ ...row, name: row.name.trim(), parentId: row.parentId || null, quantity: 1, tagIds: [] });
        }
        equipmentCreateFlow.begin({''')
    once('        equipmentIntent.value = equipmentCreateFlow.pending();\n      } catch (error)',
         '''        equipmentIntent.value = equipmentCreateFlow.pending();
        relatedIntent.value = related.pending();
      } catch (error)''')
    once('      } catch (error) { toast.error((error as Error).message || "Resolve the pending equipment create first."); return; }',
         '''      } catch (error) {
        if (!equipmentCreateFlow?.pending() && relatedFlow?.pending() && !relatedFlow.pending().main_entity_id) relatedFlow.clearBeforeMain();
        toast.error((error as Error).message || "Resolve the pending equipment create first."); return;
      }''')
    once('      if (equipmentCreateFlow) { equipmentIntent.value = equipmentCreateFlow.markNativeRejected(error); }',
         '''      if (equipmentCreateFlow) {
        equipmentIntent.value = equipmentCreateFlow.markNativeRejected(error);
        if (!equipmentIntent.value && relatedFlow?.pending() && !relatedFlow.pending().main_entity_id) {
          relatedFlow.clearBeforeMain(); relatedIntent.value = null;
        }
      }''')
    once('        equipmentCreateFlow.recordCreated(data.id);\n        equipmentIntent.value = equipmentCreateFlow.pending();',
         '''        equipmentCreateFlow.recordCreated(data.id);
        equipmentIntent.value = equipmentCreateFlow.pending();
        if (relatedFlow?.pending()?.steps.length) {
          relatedFlow.recordMainCreated(data.id);
          relatedIntent.value = relatedFlow.pending();
        }''')
    once('    toast.success(\n      t("components.entity.create_modal.toast.create_success", {',
         '''    if (relatedIntent.value?.steps.length) {
      try { await (await getRelatedFlow()).resumeRelatedSteps(); relatedIntent.value = relatedFlow?.pending(); }
      catch (relatedError) {
        relatedIntent.value = relatedFlow?.pending();
        loading.value = false;
        toast.error(`Main item saved; related item needs review: ${(relatedError as Error).message}`);
        return;
      }
    }
    toast.success(
      t("components.entity.create_modal.toast.create_success", {''')
    once('      <section v-if="equipmentIntent"', '''      <section v-if="!selectedEntityType?.isLocation" class="space-y-2" aria-label="Related items">
        <h3 class="font-medium">Related items</h3>
        <div v-for="(related, index) in stagedRelated" :key="index" class="space-y-2 rounded border p-2">
          <label>Related item name <input v-model="related.name" class="w-full rounded border p-1" /></label>
          <label>Related item type <select v-model="related.entityTypeId" class="w-full rounded border p-1"><option v-for="type in entityTypes.filter(t => !t.isLocation)" :key="type.id" :value="type.id">{{ type.name }}</option></select></label>
          <label>Related item location <select v-model="related.parentId" class="w-full rounded border p-1"><option value="">No location</option><option v-for="location in locations" :key="location.id" :value="location.id">{{ location.name }}</option></select></label>
          <label>Related description <input v-model="related.description" class="w-full rounded border p-1" /></label>
          <label>Related manufacturer <input v-model="related.manufacturer" class="w-full rounded border p-1" /></label>
          <label>Related model number <input v-model="related.modelNumber" class="w-full rounded border p-1" /></label>
          <Button type="button" variant="ghost" @click="stagedRelated.splice(index, 1)">Remove related item</Button>
        </div>
        <Button type="button" variant="outline" @click="addStagedRelated">Stage related item</Button>
      </section>
      <section v-if="relatedIntent?.main_entity_id" class="space-y-2 rounded border p-2" aria-label="Related item recovery">
        <p>Main item saved: <a :href="`/item/${relatedIntent.main_entity_id}`">Open main item</a></p>
        <div v-for="step in relatedIntent.steps.filter((row: any) => row.state !== 'completed')" :key="step.key" class="rounded border p-2">
          <p>{{ step.kind === 'create' ? `Create ${step.item?.name}` : `Link ${step.entity_id || 'related item'}` }}: {{ step.state }}. {{ step.error }}</p>
          <template v-if="step.kind === 'create' && step.state === 'uncertain'">
            <input v-model="relatedReconcileIds[step.key]" :aria-label="`Confirmed UUID for ${step.item?.name}`" placeholder="Confirmed Homebox item UUID" />
            <Button type="button" @click="reconcileRelated(step.key)">Confirm related item</Button>
            <Button type="button" variant="outline" @click="confirmRelatedAbsent(step.key)">I confirmed no related item was created</Button>
          </template>
          <Button v-if="step.state === 'failed'" type="button" @click="retryRelated(step.key)">{{ step.kind === 'create' ? 'Retry related item create' : 'Retry this step' }}</Button>
        </div>
        <Button v-if="relatedIntent.steps.some((step: any) => step.state === 'pending' || (step.kind === 'link' && step.state === 'uncertain'))" type="button" @click="resumeRelated">Resume related items</Button>
      </section>
      <section v-if="equipmentIntent"''')
    once('    form.customRows = [];\n    suggestions.value = [];\n', '    form.customRows = [];\n    suggestions.value = [];\n    stagedRelated.value = [];\n')
    once('      equipmentIntent.value = null;\n      toast.success(`Assigned equipment ID ${result.assignment.display_id}.`);',
         '''      equipmentIntent.value = null;
      if (relatedFlow?.pending()?.main_entity_id) {
        await relatedFlow.resumeRelatedSteps();
        relatedIntent.value = relatedFlow.pending();
      }
      toast.success(`Assigned equipment ID ${result.assignment.display_id}.`);''')
    return text

def equipment_catalog_create_frontend():
    path = BUILD/'components/Entity/CreateModal.vue'
    text = path.read_text()
    if 'createEquipmentCreationFlow' in text:
        if text.count('<EquipmentTemplatePanel') != 1 or text.count('import EquipmentTemplatePanel') != 1:
            raise RuntimeError('Upstream changed: equipment catalog modal integration is partial')
        return

    model_anchor = '        <FormTextField v-model="form.modelNumber" :label="$t(\'items.model_number\')" :max-length="255" />'
    if text.count(model_anchor) != 1:
        raise RuntimeError('Upstream changed: expected one model-number field in CreateModal.vue')
    text = text.replace(model_anchor, model_anchor + '''
        <FormTextField v-model="form.modelCode" label="Equipment model code" :max-length="80" />''')
    panel_anchor = '      <p v-if="barcodeLookupMessage"'
    if text.count(panel_anchor) != 1:
        raise RuntimeError('Upstream changed: expected one barcode status anchor in CreateModal.vue')
    text = text.replace(panel_anchor, '''      <EquipmentTemplatePanel
        v-if="!selectedEntityType?.isLocation"
        v-model="equipmentTemplateId"
        :entity-type-id="selectedEntityType?.id"
        :fields="{ name: form.name, manufacturer: form.manufacturer, modelNumber: form.modelNumber, modelCode: form.modelCode, description: form.description, tags: form.tags }"
        :has-item-photo="form.photos.length > 0"
        @apply="applyEquipmentTemplate"
      />
      <section v-if="equipmentIntent" class="rounded-md border border-amber-500 p-3" role="status">
        <p v-if="equipmentIntent.state === 'assignment_pending'">The item was created. Its equipment ID still needs to be assigned.</p>
        <template v-else-if="equipmentIntent.state === 'native_create_uncertain'">
          <p>The create result is uncertain. Check inventory before creating another item.</p>
          <FormTextField v-model="reconcileEntityId" class="mt-2" label="Found native item UUID" :max-length="80" />
          <div class="mt-2 flex flex-wrap gap-2">
            <Button type="button" variant="outline" @click="reconcileEquipmentCreate">I found this item</Button>
            <Button type="button" variant="ghost" @click="confirmNoEquipmentCreate">I confirmed no item was created</Button>
          </div>
        </template>
        <template v-if="equipmentIntent.state === 'assignment_pending'">
          <p v-for="step in equipmentIntent.post_create_steps || []" :key="step.key" class="mt-1 text-sm">
            {{ step.name }}: {{ step.status }}<span v-if="step.status === 'pending' && step.key.startsWith('photo-')"> · Re-select this file if this modal was reopened.</span>
            <template v-if="step.status === 'uncertain' && !step.key.startsWith('photo-')">
              <Button type="button" size="sm" variant="outline" class="ml-2" @click="reconcileEquipmentMetadata(step)">Check saved value</Button>
            </template>
            <template v-if="step.status === 'uncertain' && step.key.startsWith('photo-')">
              <Button type="button" size="sm" variant="outline" class="ml-2" @click="reconcileEquipmentPhoto(step.key, true)">Confirm uploaded</Button>
              <Button type="button" size="sm" variant="outline" class="ml-1" @click="reconcileEquipmentPhoto(step.key, false)">Confirm not uploaded</Button>
            </template>
          </p>
          <Button type="button" variant="outline" class="mt-2" :disabled="loading" @click="retryEquipmentAssignment">Resume item follow-up and ID assignment</Button>
        </template>
      </section>
''' + panel_anchor)

    import_anchor = '  import { useI18n } from "vue-i18n";'
    if text.count(import_anchor) != 1:
        raise RuntimeError('Upstream changed: expected Vue i18n import in CreateModal.vue')
    text = text.replace(import_anchor, import_anchor + '''
  import { workshopUUID } from "~/lib/workshop-uuid";
  import { applyEquipmentTemplateDefaults, assignCreatedEquipment, confirmNoMainCreate, createEquipmentCreationFlow, equipmentTemplateStorageKey } from "~/lib/equipment-catalog";
  import EquipmentTemplatePanel from "~/components/Workshop/EquipmentTemplatePanel.vue";''')
    setup_anchor = '  const api = useUserApi();'
    if text.count(setup_anchor) != 1:
        raise RuntimeError('Upstream changed: expected user API setup in CreateModal.vue')
    text = text.replace(setup_anchor, setup_anchor + '''
  const equipmentWorkshop = useWorkshop();
  const equipmentTemplateId = ref<string | null>(null);
  const equipmentIntent = ref<any>(null);
  const reconcileEntityId = ref("");
  let equipmentFlow: ReturnType<typeof createEquipmentCreationFlow> | null = null;
  let equipmentFlowKey = "";
  let equipmentFlowContext: any = null;
  async function guardedEquipmentCreate(flow: ReturnType<typeof createEquipmentCreationFlow> | null, request: () => Promise<any>) {
    try { return await request(); }
    catch (error) {
      if (flow) equipmentIntent.value = flow.markNativeRejected(error);
      return { error };
    }
  }
  async function getEquipmentFlow() {
    const context = await equipmentWorkshop.refresh();
    const key = equipmentTemplateStorageKey(context);
    if (!equipmentFlow || equipmentFlowKey !== key) {
      const read = () => { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; } };
      equipmentFlow = createEquipmentCreationFlow({
        read,
        write: (value: unknown) => localStorage.setItem(key, JSON.stringify(value)),
        clear: () => localStorage.removeItem(key),
        assignCreated: (intent: { request_key: string; entity_id: string; template_id?: string | null; model_code?: string | null; group_id?: string | null; user_id?: string | null; identity?: string | null }) => assignCreatedEquipment(equipmentWorkshop, intent),
        completePostCreate: async (intent: { group_id: string; user_id: string; identity: string; entity_id: string; request_key: string }, step: any) => {
          const current = await equipmentWorkshop.refresh();
          if (current.group.id !== intent.group_id || current.user.id !== intent.user_id || current.identity !== intent.identity) {
            return { deferred: true, message: "Switch back to the original account and collection to resume item follow-up." };
          }
          const photo = form.photos.find((candidate: PhotoPreview) => candidate.photoName === step.name && candidate.file.size === step.size && candidate.file.lastModified === step.last_modified && candidate.primary === step.primary);
          if (!photo) return { deferred: true, message: `Re-select ${step.name} to finish the queued photo upload.` };
          return api.items.attachments.add(intent.entity_id, photo.file, photo.photoName, AttachmentTypes.Photo, photo.primary);
        },
      });
      equipmentFlowKey = key;
    }
    equipmentFlowContext = context;
    equipmentIntent.value = equipmentFlow.recover();
    return equipmentFlow;
  }
  const equipmentCollections = useCollections();
  const equipmentAuth = useAuthContext();
  watch([equipmentCollections.selectedId, () => equipmentAuth.user?.id, activeDialog], () => {
    suggestionSearchVersion++; suggestionLookup.invalidate(); suggestions.value = [];
    equipmentFlow = null;
    equipmentFlowKey = "";
    equipmentFlowContext = null;
    equipmentIntent.value = null;
    equipmentTemplateId.value = null;
    if (activeDialog.value === DialogID.CreateEntity) void getEquipmentFlow();
  });
  function applyEquipmentTemplate(template: any) {
    const defaults = applyEquipmentTemplateDefaults(template);
    equipmentTemplateId.value = template.id;
    form.name = defaults.name;
    form.manufacturer = defaults.manufacturer;
    form.modelNumber = defaults.modelNumber;
    form.modelCode = defaults.modelCode;
    form.description = defaults.description;
    form.tags = defaults.tagIds;
  }
  async function retryEquipmentAssignment() {
    loading.value = true as boolean;
    try {
      const flow = await getEquipmentFlow();
      const pending = flow.pending();
      const result = pending?.post_create_steps?.some((step: any) => step.status === "failed")
        ? await flow.retryFailedPostCreate()
        : await flow.resumeAssignment();
      equipmentIntent.value = null;
      toast.success(`Assigned equipment ID ${result.assignment.display_id}.`);
      form.photos = [];
      closeDialog(DialogID.CreateEntity);
      await navigateTo(`/item/${result.entity_id}`);
    } catch (error) { equipmentIntent.value = equipmentFlow?.pending() || null; toast.error((error as Error).message || "Equipment ID assignment failed."); }
    finally { loading.value = false; }
  }
  async function reconcileEquipmentCreate() {
    const id = reconcileEntityId.value.trim();
    if (!id) return;
    try {
      const { data, error } = await api.items.get(id);
      if (error || !data || data.id !== id || data.entityType?.isLocation || (equipmentIntent.value?.entity_type_id && data.entityType?.id !== equipmentIntent.value.entity_type_id)) {
        throw new Error("That UUID does not resolve to the expected equipment item in this collection.");
      }
      const flow = await getEquipmentFlow();
      equipmentIntent.value = flow.reconcileCreated(id);
      reconcileEntityId.value = "";
    } catch (error) { toast.error((error as Error).message || "Could not verify that native item."); }
  }
  async function confirmNoEquipmentCreate() {
    if (!window.confirm("After checking the selected collection, confirm that no item was created. This clears the pending create and allows a new attempt.")) return;
    try {
      const related = await getRelatedFlow();
      const flow = await getEquipmentFlow(); confirmNoMainCreate(flow, related); equipmentIntent.value = null; relatedIntent.value = related.pending();
    }
    catch (error) { toast.error((error as Error).message || "The pending create could not be cleared."); }
  }
  async function reconcileEquipmentMetadata(step: any) {
    try {
      const flow = await getEquipmentFlow();
      const intent = flow.pending();
      if (!intent?.entity_id) throw new Error('The created item is missing.');
      let confirmed = false;
      if (step.key === 'metadata') {
        const result = await api.items.get(intent.entity_id);
        if (result.error || !result.data) throw result.error || new Error('Could not read item fields.');
        confirmed = nativeMetadataMatches(result.data, step.draft);
      } else if (step.key === 'field-notes') {
        await persistFieldNotes(equipmentWorkshop, intent, step);
        confirmed = true;
      }
      equipmentIntent.value = flow.reconcilePostCreateStep(step.key, confirmed);
    } catch (error) { toast.error((error as Error).message || 'Could not check the saved value.'); }
  }
  async function reconcileEquipmentPhoto(stepKey: string, uploaded: boolean) {
    try { const flow = await getEquipmentFlow(); equipmentIntent.value = flow.reconcilePostCreateStep(stepKey, uploaded); }
    catch (error) { toast.error((error as Error).message || "The photo result could not be reconciled."); }
  }''')

    for anchor, replacement in (
        ('const result = await api.templates.createItem(templateData.value.id, templateRequest);',
         'const templateId = templateData.value.id;\n      const result = await guardedEquipmentCreate(equipmentCreateFlow, () => api.templates.createItem(templateId, templateRequest));'),
        ('const result = await api.items.create(out);',
         'const result = await guardedEquipmentCreate(equipmentCreateFlow, () => api.items.create(out));'),
    ):
        if text.count(anchor) != 1:
            raise RuntimeError(f'Upstream changed: expected one native item create call: {anchor}')
        text = text.replace(anchor, replacement)

    form_anchor = '    modelNumber: "",'
    if text.count(form_anchor) != 1:
        raise RuntimeError('Upstream changed: expected one modelNumber form state in CreateModal.vue')
    text = text.replace(form_anchor, form_anchor + '\n    modelCode: "",')

    loading_anchor = '    loading.value = true;'
    if text.count(loading_anchor) != 1:
        raise RuntimeError('Upstream changed: expected one create loading transition in CreateModal.vue')
    text = text.replace(loading_anchor, '''    let equipmentCreateFlow: Awaited<ReturnType<typeof getEquipmentFlow>> | null = null;
    if (!selectedEntityType.value?.isLocation) {
      if (!equipmentTemplateId.value && !form.modelCode.trim()) {
        toast.error("Enter an equipment model code or choose a saved template.");
        return;
      }
      try {
        equipmentCreateFlow = await getEquipmentFlow();
        equipmentCreateFlow.begin({
          templateId: equipmentTemplateId.value || undefined,
          modelCode: form.modelCode,
          groupId: equipmentFlowContext.group.id,
          userId: equipmentFlowContext.user.id,
          identity: equipmentFlowContext.identity,
          entityTypeId: selectedEntityType.value?.id,
          postCreateSteps: form.photos.map((photo: PhotoPreview, index: number) => ({
            key: `photo-${index}-${photo.photoName}-${photo.file.size}-${photo.file.lastModified}`,
            name: photo.photoName, size: photo.file.size, last_modified: photo.file.lastModified, primary: photo.primary,
          })),
        });
        equipmentIntent.value = equipmentCreateFlow.pending();
      } catch (error) { toast.error((error as Error).message || "Resolve the pending equipment create first."); return; }
    }
    loading.value = true;''')

    error_anchor = '''    if (error) {
      loading.value = false;'''
    if text.count(error_anchor) != 1:
        raise RuntimeError('Upstream changed: expected one native create error branch in CreateModal.vue')
    text = text.replace(error_anchor, '''    if (error) {
      if (equipmentCreateFlow) { equipmentIntent.value = equipmentCreateFlow.markNativeRejected(error); }
      loading.value = false;''')

    success_anchor = '''    toast.success(
      t("components.entity.create_modal.toast.create_success", {'''
    if text.count(success_anchor) != 1:
        raise RuntimeError('Upstream changed: expected one native create success toast in CreateModal.vue')
    text = text.replace(success_anchor, '''    if (equipmentCreateFlow) {
      try {
        equipmentCreateFlow.recordCreated(data.id);
        equipmentIntent.value = equipmentCreateFlow.pending();
        if (form.photos.length) toast.info(t("components.entity.create_modal.toast.uploading_photos", { count: form.photos.length }));
        await equipmentCreateFlow.resumeAssignment();
        equipmentIntent.value = null;
      } catch (assignmentError) {
        equipmentIntent.value = equipmentCreateFlow.pending();
        loading.value = false;
        toast.error(`The item was created but its equipment ID is pending: ${(assignmentError as Error).message}`);
        return;
      }
    }

''' + success_anchor)

    reset_anchor = '    form.modelNumber = "";'
    if text.count(reset_anchor) != 1:
        raise RuntimeError('Upstream changed: expected one modelNumber reset in CreateModal.vue')
    text = text.replace(reset_anchor, reset_anchor + '\n    form.modelCode = "";\n    equipmentTemplateId.value = null;')
    photo_upload_anchor = '    if (form.photos.length > 0) {'
    if text.count(photo_upload_anchor) != 1:
        raise RuntimeError('Upstream changed: expected one native photo upload block in CreateModal.vue')
    text = text.replace(photo_upload_anchor, '    if (selectedEntityType.value?.isLocation && form.photos.length > 0) {', 1)
    photo_upload_end = '''    }

    nameOcrGeneration++;'''
    if text.count(photo_upload_end) != 1:
        raise RuntimeError('Upstream changed: expected one native photo upload block ending in CreateModal.vue')
    text = text.replace(photo_upload_end, '''    } else if (form.photos.length > 0) {
      toast.success(t("components.entity.create_modal.toast.upload_success", { count: form.photos.length }));
    }

    nameOcrGeneration++;''', 1)
    path.write_text(smart_create_form_text(text))
    remove_equipment_template_navigation()


def prepare():
    from homebox_patchset import materialize
    native_source = materialize(UPSTREAM_ROOT)
    shutil.copytree(native_source/'frontend', BUILD, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('node_modules', '.nuxt', '.output'))
    strip_item_response_short_codes_from_update_tests()
    shutil.copytree(ROOT/'homebox-ui/overlay', BUILD, dirs_exist_ok=True)
    camera_ocr_frontend()
    shutil.copy2(ROOT/'kiosk/member-avatar.js', BUILD/'lib/member-avatar.js')
    shutil.copy2(ROOT/'kiosk/label-editor.js', BUILD/'lib/label-editor.js')
    package = json.loads((BUILD/'package.json').read_text())
    overrides = {name: '3.5.20' for name in ('vue', '@vue/runtime-core', '@vue/runtime-dom', '@vue/reactivity', '@vue/shared', '@vue/compiler-sfc', '@vue/compiler-core', '@vue/compiler-dom', '@vue/compiler-ssr', '@vue/server-renderer')}
    package.pop('pnpm', None)
    (BUILD/'package.json').write_text(json.dumps(package, indent=2)+'\n')
    (BUILD/'pnpm-workspace.yaml').write_text('overrides:\n'+''.join(f"  '{name}': {version}\n" for name, version in overrides.items()))
    if (ROOT/'homebox-ui/pnpm-lock.yaml').exists():
        shutil.copy2(ROOT/'homebox-ui/pnpm-lock.yaml', BUILD/'pnpm-lock.yaml')
    configure_ui_component_discovery()
    replace('nuxt.config.ts', 'css: ["@/assets/css/main.css"],', 'css: ["@/assets/css/main.css", "@/assets/css/workshop.css", "@/assets/css/ccrate.css"],')
    # The collection aggregate replaces the native purchase-value statistics.
    replace('pages/home/index.vue', '  import { statCardData } from "./statistics";', '  import QuickStatistics from "@/components/Home/QuickStatistics.vue";')
    replace('pages/home/index.vue', '  import StatCard from "~/components/global/StatCard/StatCard.vue";\n', '')
    replace('pages/home/index.vue', '  const stats = statCardData(api);\n', '')
    replace('pages/home/index.vue', '''      <section>
        <Subtitle> {{ $t("home.quick_statistics") }} </Subtitle>
        <div class="grid grid-cols-2 gap-2 md:grid-cols-4 md:gap-6">
          <StatCard v-for="(stat, i) in stats" :key="i" :title="stat.label" :value="stat.value" :type="stat.type" />
        </div>
      </section>''', '      <QuickStatistics />')
    # The Home dashboard shows the same current custody as the equipment terminal.
    replace('pages/home/index.vue', '  import BaseCard from', '  import CheckedOutItems from "@/components/Workshop/CheckedOutItems.vue";\n  import BaseCard from')
    replace('pages/home/index.vue', '      <section>\n        <Subtitle> {{ $t("home.recently_added") }}', '      <CheckedOutItems />\n\n      <section>\n        <Subtitle> {{ $t("home.recently_added") }}')
    # Native sidebar and quick menu, with manager-only entries hidden for members.
    navigation_frontend()
    shell_frontend()
    ocr_popover_frontend()
    location_child_contents_frontend()
    replace('layouts/default.vue', 'class="h-9 grow sm:max-w-sm"', 'class="ccrate-header-search h-11 min-w-0 grow sm:max-w-sm"')
    # Put badges on the actual existing Collection members table.
    path = 'pages/collection/index/members.vue'
    replace(path, '  const loading = ref(true);', '''  const workshop = useWorkshop();
  const { selectedId } = useCollections();
  const badgeRows = ref<any[]>([]), peopleRows = ref<any[]>([]), workshopError = ref("");
  const memberLoans = ref<WorkshopLoan[] | null>(null), itemLoading = ref(true), itemError = ref("");
  let itemRevision = 0, memberTimer: ReturnType<typeof setInterval> | null = null;
  async function loadMemberLoans() {
    const revision = ++itemRevision;
    itemLoading.value = true; itemError.value = "";
    try {
      const rows = await workshop.request<WorkshopLoan[]>("loans");
      if (revision === itemRevision) memberLoans.value = rows;
    } catch (cause) { if (revision === itemRevision) itemError.value = (cause as Error).message; }
    finally { if (revision === itemRevision) itemLoading.value = false; }
  }
  function refreshVisibleItems() { if (document.visibilityState === "visible" && !itemLoading.value) void loadMemberLoans(); }
  function refreshMembers() { void loadMembers(); void loadBadges(); void loadMemberLoans(); }
  let workshopRevision = 0;
  async function loadBadges() {
    const revision = ++workshopRevision;
    badgeRows.value = []; peopleRows.value = []; workshopError.value = "";
    try {
      await workshop.refresh();
      if (!workshop.manager.value) return;
      const [badges, people] = await Promise.all([workshop.request<any[]>("badges"), workshop.request<any[]>("people")]);
      if (revision === workshopRevision) { badgeRows.value = badges; peopleRows.value = people; }
    } catch (cause) { if (revision === workshopRevision) workshopError.value = (cause as Error).message; }
  }
  watch(selectedId, () => { memberLoans.value = null; refreshMembers(); }, { flush: "sync" });
  onMounted(() => {
    void loadMemberLoans();
    window.addEventListener("focus", refreshVisibleItems);
    document.addEventListener("visibilitychange", refreshVisibleItems);
    memberTimer = setInterval(refreshVisibleItems, 30000);
  });
  onBeforeUnmount(() => {
    workshopRevision++; itemRevision++; memberLoans.value = null;
    if (memberTimer) clearInterval(memberTimer);
    window.removeEventListener("focus", refreshVisibleItems);
    document.removeEventListener("visibilitychange", refreshVisibleItems);
  });

  const loading = ref(true);''')
    replace(path, '<TableCell>{{ user.name }}</TableCell>', '<TableCell><div class="flex items-center gap-3"><MemberAvatar :member-id="user.id" :name="user.name" /><span class="font-medium">{{ user.name }}</span></div></TableCell>')
    replace(path, '  import { Button }', '  import MemberAvatar from "@/components/Workshop/MemberAvatar.vue";\n  import MemberItems from "@/components/Workshop/MemberItems.vue";\n  import type { WorkshopLoan } from "@/lib/workshop-loans";\n  import BadgeActions from "@/components/Workshop/BadgeActions.vue";\n  import { Button }')
    replace(path, '    loadMembers();\n  });', '    loadMembers();\n    loadBadges();\n  });')
    replace(path, '  <div class="space-y-4">', '''  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-sm text-muted-foreground">Members, kiosk badges and the items each person has checked out.</p>
      <Button variant="outline" size="sm" :disabled="loading || itemLoading" @click="refreshMembers">Refresh members &amp; items</Button>
    </div>
    <p v-if="itemError" role="alert" class="text-sm text-destructive">Could not load checked-out items. {{ itemError }}</p>
    <p v-if="workshopError" role="alert" class="text-sm text-destructive">Badge management: {{ workshopError }} <Button variant="link" @click="loadBadges">Reload badge management</Button></p>''')
    replace(path, '<TableHead>{{ $t("collection.members.name") }}</TableHead>', '<TableHead>User</TableHead>')
    replace(path, '              <TableHead class="w-32', '              <TableHead v-if="workshop.manager.value">Kiosk Badge</TableHead>\n              <TableHead>Items</TableHead>\n              <TableHead class="w-32')
    replace(path, '              <TableCell>\n                <div class="ml-auto">', '''              <TableCell v-if="workshop.manager.value">
                <BadgeActions :member="user" :badges="badgeRows.filter(row => row.user_id === user.id)" :can-manage="!!peopleRows.find(row => row.id === user.id)?.workshop_manager" :protected-owner="!!peopleRows.find(row => row.id === user.id)?.protected_owner" @changed="loadBadges" />
              </TableCell>
              <TableCell><MemberItems :member-id="user.id" :loans="memberLoans" :loading="itemLoading" :error="itemError" /></TableCell>
              <TableCell>
                <div class="ml-auto">''')
    # Item loans sit alongside native Details/Maintenance/Edit; details show status.
    path = 'pages/item/[id]/index.vue'
    item_log_frontend()
    replace(path, '        id: "edit",', '        id: "loans", name: "Loans & return notes", to: `/item/${itemId.value}/loans`,\n      },\n      {\n        id: "edit",')
    replace(path, '{{ $t(tab.name) }}', '{{ tab.id === "loans" ? tab.name : $t(tab.name) }}')
    replace(path, ':id="item.assetId"\n                type="asset"', ':id="item.assetId"\n                :entity-id="item.id"\n                type="asset"')
    replace(path, '<NuxtPage :item="item" :page-key="itemId" />', '<NuxtPage :item="item" :page-key="itemId" />\n        <ItemLoans v-if="!hasNested" :item-id="itemId" activity-mode="details" />')
    # Extend the existing label dialog; browser printing remains native.
    path = 'components/global/LabelMaker.vue'
    replace(path, '  import PageQRCode', '  import PiPrint from "@/components/Workshop/PiPrint.vue";\n  import PageQRCode')
    replace(path, '    id: string;', '    id: string;\n    entityId?: string;')
    replace(path, '        <img :src="getLabelUrl(false)" />', '<img :src="getLabelUrl(false)" alt="Homebox label preview" />\n        <PiPrint :id="id" :entity-id="entityId" />')
    replace(path, '<Button size="icon" @click="openDialog(DialogID.PrintLabel)">', '<Button size="icon" :aria-label="$t(\'components.global.label_maker.browser_print\')" @click="openDialog(DialogID.PrintLabel)">')
    # Manage native people beside badges and custody, with collection-owner access.
    contract=BUILD/'lib/api/types/data-contracts.ts';body=contract.read_text()
    start=body.index('export interface UserSummary {');end=body.index('\n}',start)
    body=body[:end]+'\n  avatar?: string;'+body[end:];contract.write_text(body)
    path='pages/collection/index/members.vue';target=BUILD/path;body=target.read_text()
    body=body.replace('  import MemberAvatar from', '  import UserManager from "@/components/Workshop/UserManager.vue";\n  import MemberAvatar from')
    body=body.replace('  const workshop = useWorkshop();', '  const workshop = useWorkshop();\n  const userAdmin = ref(false), userManager = ref<InstanceType<typeof UserManager> | null>(null);')
    body=body.replace('const [badges, people] = await Promise.all([workshop.request<any[]>("badges"), workshop.request<any[]>("people")]);','const [badges, people, administration] = await Promise.all([workshop.request<any[]>("badges"), workshop.request<any[]>("people"), workshop.request<{ canManage: boolean }>("users/administration")]);')
    body=body.replace('badgeRows.value = badges; peopleRows.value = people;', 'badgeRows.value = badges; peopleRows.value = people; userAdmin.value = administration.canManage;')
    body=body.replace('if (!workshop.manager.value) return;', 'if (!workshop.manager.value) { userAdmin.value = false; return; }')
    body=body.replace('watch(selectedId, () => { memberLoans.value = null;', 'watch(selectedId, () => { userAdmin.value = false; memberLoans.value = null;')
    body=body.replace('      <Button variant="outline" size="sm" :disabled="loading || itemLoading"', '      <Button v-if="userAdmin" variant="outline" size="sm" @click="userManager?.show()">Manage users</Button>\n      <Button variant="outline" size="sm" :disabled="loading || itemLoading"')
    body=body.replace('    <p v-if="itemError"', '    <UserManager v-if="userAdmin" ref="userManager" :members="members" @changed="refreshMembers" />\n    <p v-if="itemError"')
    body=body.replace('<MemberAvatar :member-id="user.id" :name="user.name" /><span class="font-medium">{{ user.name }}</span>', '<MemberAvatar :member-id="user.id" :name="user.name" :picture="user.avatar" /><span><span class="block font-medium">{{ user.name }}</span><span class="block text-xs text-muted-foreground">ID {{ user.id.slice(0,8) }}</span></span>')
    body=body.replace('<TableCell>{{ user.email }}</TableCell>', '<TableCell>{{ user.email || "—" }}</TableCell>')
    body=body.replace('                <div class="ml-auto">','                <div class="ml-auto flex items-center justify-end gap-2">\n                  <Button v-if="userAdmin" variant="outline" size="sm" :aria-label="\'Manage profile: \' + user.name" @click="userManager?.show(user)">Manage profile</Button>')
    body=body.replace(':disabled="removing[user.id] || (isLastMember && user.id === currentUserId)"', ':disabled="!userAdmin || removing[user.id] || user.id === currentUserId || !!peopleRows.find(row => row.id === user.id)?.protected_owner"')
    body=body.replace('  const loading = ref(true);', '  let memberRevision = 0;\n  const loading = ref(true);')
    body=body.replace('const loadMembers = async () => {', 'const loadMembers = async () => {\n    const revision = ++memberRevision;')
    body=body.replace('const res = await api.group.getMembers();', 'const res = await api.group.getMembers();\n      if (revision !== memberRevision) return;')
    start=body.index('  const loadMembers = async () => {');end=body.index('  const handleRemove',start)
    part=body[start:end].replace('    } catch (e) {','    } catch (e) {\n      if (revision !== memberRevision) return;').replace('      loading.value = false;', '      if (revision === memberRevision) loading.value = false;')
    body=body[:start]+part+body[end:]
    body=body.replace('workshopRevision++; itemRevision++;', 'memberRevision++; workshopRevision++; itemRevision++;')
    body=body.replace('watch(selectedId, () => { userAdmin.value = false;', 'watch([selectedId, () => auth.user?.id], () => { members.value = []; userAdmin.value = false;')
    target.write_text(body)
    nest_frontend()
    equipment_catalog_create_frontend()
    equipment_assigned_ids_frontend()
    grouped_inventory_frontend()
    item_action_surfaces_frontend()
    item_metadata_detail_frontend()
    brand_frontend()


def prepare_source_workspace(destination, upstream_root=ROOT):
    """Apply the release UI source and overlay steps in a separate workspace."""
    global BUILD, UPSTREAM_ROOT
    previous_build, previous_upstream = BUILD, UPSTREAM_ROOT
    BUILD, UPSTREAM_ROOT = pathlib.Path(destination), pathlib.Path(upstream_root)
    try:
        prepare()
    finally:
        BUILD, UPSTREAM_ROOT = previous_build, previous_upstream


def configure_oxc_wasi_binding(workspace, toolchain_root):
    # oxc-parser 0.72's native ARM binding requires instructions absent on this Pi.
    wasi = toolchain_root/'oxc-wasi/node_modules/@oxc-parser/binding-wasm32-wasi'
    binding = workspace/'node_modules/.pnpm/oxc-parser@0.72.3/node_modules/oxc-parser/bindings.js'
    if wasi.exists() and binding.is_file():
        source = binding.read_text()
        anchor = 'nativeBinding = requireNative()'
        if anchor in source:
            binding.write_text(source.replace(anchor, 'nativeBinding = require('+repr(str(wasi))+')'))


def run_frontend_command(command, *, cwd, env):
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    def forward(source, destination):
        try:
            for line in source:
                line = filter_known_wasi_warning(line)
                if line:
                    destination.write(line)
                    destination.flush()
        finally:
            source.close()

    output_threads = [
        threading.Thread(target=forward, args=(process.stdout, sys.stdout)),
        threading.Thread(target=forward, args=(process.stderr, sys.stderr)),
    ]
    for thread in output_threads:
        thread.start()
    returncode = process.wait()
    for thread in output_threads:
        thread.join()
    if returncode:
        print(f'Frontend command failed with exit code {returncode}.', file=sys.stderr, flush=True)
        raise subprocess.CalledProcessError(returncode, command)
    return subprocess.CompletedProcess(command, returncode)



def build():
    global BUILD, TOOLCHAIN_ROOT, UPSTREAM_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument('--toolchain-root', type=pathlib.Path, default=TOOLCHAIN_ROOT)
    parser.add_argument('--upstream-root', type=pathlib.Path, default=UPSTREAM_ROOT)
    parser.add_argument('--build-root', type=pathlib.Path, help='use a new or empty frontend workspace for disposable validation')
    parser.add_argument('--prepare', action='store_true', help='prepare dependencies without running typecheck or build')
    args = parser.parse_args()
    if args.build_root is not None and args.build_root.exists() and (
        not args.build_root.is_dir() or any(args.build_root.iterdir())
    ):
        parser.error('--build-root must be empty so stale files cannot contaminate a disposable build')
    if args.build_root is not None:
        BUILD = args.build_root.resolve()
    TOOLCHAIN_ROOT, UPSTREAM_ROOT = args.toolchain_root.resolve(), args.upstream_root.resolve()
    node = pathlib.Path((TOOLCHAIN_ROOT/'node-path.txt').read_text().strip())
    env = dict(os.environ, PATH=str(node/'bin')+os.pathsep+os.environ['PATH'])
    pnpm = resolve_pnpm_launcher(TOOLCHAIN_ROOT)
    print('Preparing frontend source workspace...', flush=True)
    prepare()
    if args.build_root is not None:
        print('Installing frontend dependencies in disposable workspace...', flush=True)
        run_frontend_command([str(pnpm), 'install', '--frozen-lockfile', '--ignore-scripts'], cwd=BUILD, env=env)
        print('Frontend dependencies installed.', flush=True)
    configure_oxc_wasi_binding(BUILD, TOOLCHAIN_ROOT)
    print('Preparing Nuxt components...', flush=True)
    run_frontend_command([str(pnpm), 'exec', 'nuxt', 'prepare'], cwd=BUILD, env=env)
    print('Nuxt preparation complete.', flush=True)
    if not args.prepare:
        print('Running frontend typecheck...', flush=True)
        result = subprocess.run([str(pnpm), 'exec', 'nuxi', 'typecheck'], cwd=BUILD, env=env, capture_output=True, text=True)
        typecheck_output = result.stdout + result.stderr
        typecheck_log = BUILD/'homebox-ui-typecheck.log' if args.build_root is not None else ROOT/'work/homebox-ui-typecheck.log'
        typecheck_log.write_text(typecheck_output)
        if has_frontend_tool_failure(typecheck_output):
            print(typecheck_output)
            print(f'Frontend typecheck tool failed with exit code {result.returncode}.', file=sys.stderr, flush=True)
            raise RuntimeError('Frontend typecheck could not be invoked successfully.')
        diagnostics = [list(match.groups()) for match in re.finditer(r'^(.+?)\(\d+,\d+\): error (TS\d+): (.*)$', typecheck_output, re.M)]
        if result.returncode:
            baseline = json.loads((ROOT/'homebox-ui/upstream-typecheck.json').read_text())
            pin = source_commit(UPSTREAM_ROOT/'upstream/homebox')
            if result.returncode != 1 or not is_only_known_upstream_typecheck_failure(typecheck_output, baseline, pin):
                print(typecheck_output)
                print(f'Frontend typecheck failed with exit code {result.returncode}.', file=sys.stderr, flush=True)
                raise RuntimeError('Frontend typecheck introduced errors or its upstream baseline changed.')
            print(f'Typecheck: no added diagnostics; {len(diagnostics)} pre-existing upstream diagnostics.', flush=True)
        else:
            print('Frontend typecheck passed.', flush=True)
        print('Building frontend...', flush=True)
        run_frontend_command([str(pnpm), 'run', 'build'], cwd=BUILD, env=env)
        print('Frontend build completed successfully.', flush=True)

if __name__ == '__main__':
    build()
