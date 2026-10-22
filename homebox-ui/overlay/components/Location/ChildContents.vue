<script setup lang="ts">
  import type { EntitySummary } from "~~/lib/api/types/data-contracts";
  import { createChildItemHydrator, groupChildItems } from "~~/lib/child-item-groups";
  import ItemQuickActions from "@/components/Workshop/ItemQuickActions.vue";
  import { useItemActions } from "@/composables/use-item-actions";
  import { useWorkshop } from "@/composables/use-workshop";
  import type { ItemActionStatus } from "@/lib/item-action-contracts";
  import { recentItemNotes } from "@/lib/item-activity-notes.js";

  type ChildItem = EntitySummary & { manufacturer?: string; modelNumber?: string; serialNumber?: string; metadataPending?: boolean; metadataUnavailable?: boolean };
  type ChildHydrator = (items: ChildItem[]) => Promise<ChildItem[]>;

  type LocationNode = Pick<EntitySummary, "id" | "name" | "itemCount"> & {
    children?: LocationNode[];
  };

  defineOptions({ name: "ChildContents" });
  type PreviewState = { expanded: boolean; loading: boolean; loaded: boolean; items: EntitySummary[]; children: LocationNode[]; error: string; metadataFailed?: boolean };
  const props = withDefaults(defineProps<{ locations: LocationNode[]; depth?: number; filter?: string; parentPath?: string; loadedStates?: Map<string, PreviewState>; hydrator?: ChildHydrator; directOnly?: boolean; heading?: string }>(), { depth: 0, filter: "", parentPath: "", directOnly: false, heading: "Child locations" });
  const isRoot = props.depth === 0;
  const api = useUserApi();
  const workshop = useWorkshop();
  const itemActions = useItemActions();
  const actionStatuses = reactive(new Map<string, ItemActionStatus>());
  const recentNotes = reactive(new Map<string, string>());
  const hydrateChildItems = props.hydrator ?? createChildItemHydrator((id: string) => api.items.get(id));
  const states = props.loadedStates ?? reactive(new Map<string, PreviewState>());
  const directItems = reactive(new Map<string, EntitySummary[]>());
  const loading = ref(false);
  const error = ref("");
  const partial = ref(false);
  const metadataFailed = ref(false);
  const batchLoaded = ref(false);
  const allExpanded = ref(isRoot);
  const filterText = ref("");
  const filterId = useId();
  const expandedGroups = reactive(new Set<string>());
  const actionGenerations = new Map<string, number>();
  const noteGenerations = new Map<string, number>();
  const failedImages = reactive(new Set<string>());
  const actionIdentity = () => `${workshop.context.value?.user.id || ""}:${workshop.context.value?.group.id || ""}:${workshop.context.value?.identity || ""}`;
  const searchTerm = computed(() => (isRoot ? filterText.value : props.filter).trim().toLocaleLowerCase());
  function actionStatusLabel(id: string) {
    const status = actionStatuses.get(id);
    if (!status) return "";
    return status.availability === "checked_out" ? "Checked out" : status.availability === "available" ? "Available for checkout" : status.availability === "blocked" ? (status.blocker || "Blocked") : "Status unknown";
  }

  watch(itemActions.changed, async result => {
    if (!result || result.kind === "cart") return;
    const identity = actionIdentity();
    const loaded = [...directItems.values(), ...[...states.values()].map(state => state.items)].flat();
    const loadedIds = new Set(loaded.map(item => item.id));
    for (const id of result.itemIds) {
      if (!loadedIds.has(id)) continue;
      const revision = (actionGenerations.get(id) || 0) + 1;
      actionGenerations.set(id, revision);
      const noteRevision = (noteGenerations.get(id) || 0) + 1;
      noteGenerations.set(id, noteRevision);
      try {
        const [status, response, history] = await Promise.all([
          itemActions.loadStatus(id, true), api.items.get(id), workshop.request<any[]>("history?entity=" + encodeURIComponent(id)),
        ]);
        if (revision !== actionGenerations.get(id) || identity !== actionIdentity()) continue;
        actionStatuses.set(id, status);
        const detail = response?.data ?? response;
        if (!response?.error && detail?.id === id) {
          const moved = { ...detail, ...(await hydrateChildItems([detail as ChildItem]))[0] } as ChildItem;
          if (revision !== actionGenerations.get(id) || identity !== actionIdentity()) continue;
          for (const [parentId, items] of directItems) directItems.set(parentId, items.filter(item => item.id !== id));
          for (const state of states.values()) state.items = state.items.filter(item => item.id !== id);
          const parentId = moved.parent?.id;
          if (parentId && directItems.has(parentId)) directItems.set(parentId, [...directItems.get(parentId)!.filter(item => item.id !== id), moved]);
          else if (parentId && states.get(parentId)?.loaded) states.get(parentId)!.items = [...states.get(parentId)!.items.filter(item => item.id !== id), moved];
          if (noteRevision === noteGenerations.get(id)) recentNotes.set(id, recentItemNotes(Array.isArray(history) ? history : [], id, 1)[0]?.text || "");
        }
      }
      catch { if (revision === actionGenerations.get(id)) actionStatuses.delete(id); }
    }
  });

  function itemsFor(location: LocationNode, nested = false): EntitySummary[] {
    return isRoot && !nested ? (directItems.get(location.id) || []) : stateFor(location.id).items;
  }

  function matchesItem(item: ChildItem) {
    const term = searchTerm.value;
    const productGroupNames = (item.tags || []).map(tag => String(tag?.name || ""))
      .filter(name => name.toLocaleLowerCase().startsWith("c-crate product group: "))
      .map(name => name.slice("C-Crate Product group: ".length));
    return !term || [item.name, item.displayId, item.assetId, item.manufacturer, item.modelNumber, item.serialNumber, ...productGroupNames]
      .some(value => String(value || "").toLocaleLowerCase().includes(term));
  }

  function visibleItems(location: LocationNode) {
    return groupChildItems(itemsFor(location) as ChildItem[]).map(group => ({ ...group, matchingItems: group.items.filter(matchesItem) })).filter(group => group.matchingItems.length);
  }

  function groupStateKey(locationId: string, groupKey: string) {
    return JSON.stringify([locationId, groupKey]);
  }

  function groupExpanded(locationId: string, group: { key: string; matchingItems: ChildItem[] }) {
    return searchTerm.value ? group.matchingItems.length > 0 : expandedGroups.has(groupStateKey(locationId, group.key));
  }

  function toggleGroup(location: LocationNode, groupKey: string) {
    if (searchTerm.value) return;
    const key = groupStateKey(location.id, groupKey);
    if (expandedGroups.has(key)) expandedGroups.delete(key);
    else {
      expandedGroups.add(key);
      const group = visibleItems(location).find(row => row.key === groupKey);
      if (group) void loadRecentNotes(group.matchingItems.map((item: ChildItem) => item.id));
    }
  }

  async function loadRecentNotes(ids: string[]) {
    const identity = actionIdentity();
    const revisions = new Map(ids.map(id => {
      const revision = (noteGenerations.get(id) || 0) + 1;
      noteGenerations.set(id, revision);
      return [id, revision] as const;
    }));
    let cursor = 0;
    const workers = Array.from({ length: Math.min(4, ids.length) }, async () => {
      while (cursor < ids.length) {
        const id = ids[cursor++]!;
        try {
          const rows = await workshop.request<any[]>("history?entity=" + encodeURIComponent(id));
          if (revisions.get(id) !== noteGenerations.get(id) || identity !== actionIdentity()) continue;
          recentNotes.set(id, recentItemNotes(Array.isArray(rows) ? rows : [], id, 1)[0]?.text || "");
        } catch { if (revisions.get(id) === noteGenerations.get(id) && identity === actionIdentity()) recentNotes.set(id, ""); }
      }
    });
    await Promise.all(workers);
  }

  function itemImage(item: ChildItem) {
    const attachmentId = item.thumbnailId || item.imageId;
    return attachmentId ? api.authURL(`/entities/${item.id}/attachments/${attachmentId}`) : "";
  }

  function hasItemImage(item: ChildItem) { return Boolean(itemImage(item) && !failedImages.has(item.id)); }

  function groupPhoto(group: { items: ChildItem[]; matchingItems: ChildItem[] }) {
    return group.matchingItems.find(hasItemImage) || group.items.find(hasItemImage) || null;
  }

  function failItemImage(item: ChildItem) { failedImages.add(item.id); }

  function matchesLocationName(location: LocationNode) {
    return Boolean(searchTerm.value) && location.name.toLocaleLowerCase().includes(searchTerm.value);
  }

  function hasLoadedMatch(location: LocationNode, nested = false): boolean {
    if (matchesLocationName(location) || itemsFor(location, nested).some(matchesItem)) return true;
    const state = stateFor(location.id);
    return state.loaded && state.children.some(child => hasLoadedMatch(child, true));
  }

  function filteredLocations() {
    if (!searchTerm.value) return props.locations;
    return props.locations.filter(location => hasLoadedMatch(location));
  }

  function isExpandedForDisplay(location: LocationNode) {
    return stateFor(location.id).expanded || Boolean(searchTerm.value && hasLoadedMatch(location));
  }

  function isForcedOpenByFilter(location: LocationNode) {
    return Boolean(searchTerm.value && hasLoadedMatch(location));
  }

  function canCollapseAll() {
    return !(searchTerm.value && filteredLocations().length > 0);
  }

  function locationPath(name: string) {
    return [props.parentPath, name].filter(Boolean).join(" / ");
  }

  function stateFor(locationId: string) {
    let state = states.get(locationId);
    if (!state) {
      state = { expanded: isRoot, loading: false, loaded: false, items: [], children: [], error: "" };
      states.set(locationId, state);
    }
    return state;
  }

  async function loadItems() {
    if (loading.value || batchLoaded.value) return;
    loading.value = true;
    error.value = "";
    partial.value = false;
    metadataFailed.value = false;
    const immediateChildIds = props.locations.map(location => location.id);
    const collected = new Map(immediateChildIds.map(id => [id, [] as EntitySummary[]]));
    let page = 1;
    try {
      let total = 0;
      let received = 0;
      do {
        const response = await api.items.getAll({ parentIds: immediateChildIds, page, pageSize: 100, includeArchived: true });
        if (response.error || !response.data) throw new Error("request failed");
        total = response.data.total;
        received += response.data.items.length;
        if (!response.data.items.length && received < total) throw new Error("incomplete page");
        for (const item of response.data.items) {
          const parentId = item.parent?.id;
          if (!parentId) continue;
          collected.get(parentId)?.push(item);
        }
        if (!response.data.items.length) break;
        page++;
      } while (received < total);
      const allItems = [...collected.values()].flat();
      for (const [id, items] of collected) directItems.set(id, items.map(item => ({ ...item, metadataPending: true })));
      const hydratedItems = await hydrateChildItems(allItems as ChildItem[]);
      metadataFailed.value = hydratedItems.some(item => item.metadataUnavailable);
      const byId = new Map(hydratedItems.map(item => [item.id, item]));
      for (const [id, items] of collected) directItems.set(id, items.map(item => byId.get(item.id) || item));
      batchLoaded.value = true;
      void loadRecentNotes(allItems.map(item => item.id));
    } catch {
      for (const [id, items] of collected) directItems.set(id, items.map(item => ({ ...item, metadataPending: false, metadataUnavailable: true })));
      partial.value = [...collected.values()].some(items => items.length > 0);
      metadataFailed.value = partial.value;
      error.value = partial.value
        ? "Some location contents could not be loaded. Results may be incomplete."
        : "Could not load location contents. Try again.";
    } finally {
      loading.value = false;
    }
  }

  async function loadDetail(locationId: string) {
    const state = stateFor(locationId);
    if (state.loading || state.loaded) return;
    state.loading = true;
    state.error = "";
    try {
      if (!props.directOnly) {
        const detail = await api.items.getLocation(locationId);
        if (detail.error || !detail.data) throw new Error("request failed");
        state.children = detail.data.children || [];
      }
      if (!isRoot) {
        const collected = [] as EntitySummary[];
        let page = 1;
        let total = 0;
        let received = 0;
        do {
          const response = await api.items.getAll({ parentIds: [locationId], page, pageSize: 100, includeArchived: true });
          if (response.error || !response.data) throw new Error("request failed");
          total = response.data.total;
          received += response.data.items.length;
          if (!response.data.items.length && received < total) throw new Error("incomplete page");
          collected.push(...response.data.items.filter(item => item.parent?.id === locationId));
          state.items = collected.map(item => ({ ...item, metadataPending: true }));
          page++;
        } while (received < total);
        state.items = await hydrateChildItems(collected as ChildItem[]);
        state.metadataFailed = state.items.some((item: ChildItem) => item.metadataUnavailable);
        void loadRecentNotes(state.items.map(item => item.id));
      }
      state.loaded = true;
    } catch {
      if (state.items.length) {
        state.items = state.items.map((item: ChildItem) => ({ ...item, metadataPending: false, metadataUnavailable: true }));
        state.metadataFailed = true;
      }
      state.error = state.items.length
        ? "Some location contents could not be loaded. Results may be incomplete."
        : "Could not load this location's details. Try again.";
    } finally {
      state.loading = false;
    }
  }

  function toggle(location: LocationNode) {
    if (isForcedOpenByFilter(location)) return;
    const locationId = location.id;
    const state = stateFor(locationId);
    state.expanded = !state.expanded;
    allExpanded.value = props.locations.every(location => stateFor(location.id).expanded);
    if (state.expanded && !isRoot) void loadDetail(locationId);
    else if (state.expanded && state.loaded === false) void loadDetail(locationId);
  }

  function setAllExpanded(expanded: boolean) {
    if (!expanded && !canCollapseAll()) return;
    allExpanded.value = expanded;
    for (const location of props.locations) {
      const state = stateFor(location.id);
      state.expanded = expanded;
      if (expanded && !state.loaded) void loadDetail(location.id);
    }
  }

  function retryBatch() {
    batchLoaded.value = false;
    void loadItems();
  }

  function retryDetail(locationId: string) {
    const state = stateFor(locationId);
    state.loaded = false;
    void loadDetail(locationId);
  }

  onMounted(() => {
    if (!isRoot) return;
    for (const location of props.locations) directItems.set(location.id, []);
    void loadItems();
    for (const location of props.locations) void loadDetail(location.id);
  });
</script>

<template>
  <section v-if="props.locations.length" class="mt-6 space-y-3" :aria-label="props.heading">
    <h2 class="text-lg font-semibold">{{ props.heading }}</h2>
    <div v-if="isRoot" class="flex flex-wrap items-center gap-2">
      <label class="sr-only" :for="filterId">{{ props.directOnly ? "Filter loaded items" : "Filter loaded cabinet contents" }}</label>
      <input :id="filterId" v-model="filterText" type="search" :aria-label="props.directOnly ? 'Filter loaded items' : 'Filter loaded cabinet contents'" :placeholder="props.directOnly ? 'Filter loaded items' : 'Filter loaded contents'" class="min-w-0 flex-1 rounded border bg-background px-3 py-2 text-sm" />
      <button v-if="filterText" type="button" class="text-sm underline" @click="filterText = ''">Clear filter</button>
      <p class="basis-full text-xs text-muted-foreground">{{ props.directOnly ? "Search covers loaded items in this location." : "Search covers loaded cabinet contents only; expand bins to load deeper locations." }}</p>
    </div>
    <div v-if="!props.directOnly" class="flex flex-wrap gap-3">
      <button type="button" class="text-sm underline disabled:cursor-not-allowed disabled:opacity-50" :aria-expanded="allExpanded" :disabled="!canCollapseAll()" :aria-label="canCollapseAll() ? 'Collapse all bins' : 'Clear the filter to enable collapsing matching bins'" @click="setAllExpanded(false)">Collapse all bins</button>
      <button type="button" class="text-sm underline" :aria-expanded="allExpanded" @click="setAllExpanded(true)">Expand bins</button>
    </div>
    <p v-if="isRoot && !props.directOnly && !canCollapseAll()" role="status" class="text-xs text-muted-foreground">Clear the filter to enable collapsing matching bins.</p>
    <p v-if="loading" role="status" aria-live="polite" class="text-sm text-muted-foreground">Loading location and item details…</p>
    <div v-if="error" role="alert" class="flex flex-wrap items-center gap-2 text-sm">
      <span>{{ error }}</span>
      <button type="button" class="underline" @click="retryBatch">Retry</button>
    </div>
    <div v-if="isRoot && metadataFailed" role="alert" class="flex flex-wrap items-center gap-2 text-sm">
      <span>Some item details could not be loaded. Those records remain separate until retry.</span>
      <button type="button" class="underline" @click="retryBatch">Retry item details</button>
    </div>
    <p v-if="searchTerm && filteredLocations().length === 0" role="status" class="text-sm text-muted-foreground">No loaded locations match this filter.</p>
    <article v-for="location in filteredLocations()" :key="location.id" class="overflow-hidden rounded-lg border bg-card">
      <header class="flex flex-wrap items-center gap-2 p-3">
        <button
          type="button"
          class="rounded px-2 py-1 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          :aria-expanded="isExpandedForDisplay(location)"
          :disabled="isForcedOpenByFilter(location)"
          :aria-label="isForcedOpenByFilter(location) ? `Expanded for filter match in ${location.name}; clear the filter to enable collapse` : `${isExpandedForDisplay(location) ? 'Collapse' : 'Expand'} contents of ${location.name}`"
          @click="toggle(location)"
        >
          <span aria-hidden="true">{{ isExpandedForDisplay(location) ? "▾" : "▸" }}</span>
        </button>
        <NuxtLink :to="`/location/${encodeURIComponent(location.id)}`" class="min-w-0 flex-1 font-medium hover:underline">
          {{ location.name }}
        </NuxtLink>
        <span v-if="matchesLocationName(location)" class="rounded bg-accent px-2 py-0.5 text-xs text-muted-foreground">Bin name match</span>
        <span v-if="location.itemCount > 0" class="text-sm text-muted-foreground">{{ location.itemCount }} items</span>
      </header>

      <div v-if="isExpandedForDisplay(location)" class="border-t bg-muted/20 p-3 pl-10">
        <p v-if="stateFor(location.id).loading" role="status" aria-live="polite" class="text-sm text-muted-foreground">Loading location details…</p>
        <div v-if="stateFor(location.id).error" role="alert" class="flex flex-wrap items-center gap-2 text-sm">
          <span>{{ stateFor(location.id).error }}</span>
          <button type="button" class="underline" @click="retryDetail(location.id)">Retry</button>
        </div>
        <div v-if="stateFor(location.id).metadataFailed" role="alert" class="flex flex-wrap items-center gap-2 text-sm">
          <span>Some item details could not be loaded. Those records remain separate until retry.</span>
          <button type="button" class="underline" @click="retryDetail(location.id)">Retry item details</button>
        </div>
        <p v-if="!stateFor(location.id).error && !stateFor(location.id).loading && itemsFor(location).length === 0 && stateFor(location.id).children.length === 0 && (isRoot ? batchLoaded : stateFor(location.id).loaded)" class="text-sm text-muted-foreground">This location is empty.</p>
        <ul v-if="visibleItems(location).length" class="divide-y">
          <li v-for="group in visibleItems(location)" :key="group.key" class="py-2 first:pt-0 last:pb-0">
            <template v-if="group.items.length > 1">
              <button type="button" class="flex w-full min-w-0 items-center gap-3 rounded text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-70" :aria-expanded="groupExpanded(location.id, group)" :disabled="Boolean(searchTerm)" :aria-label="searchTerm ? `Expanded for filter match in ${group.name}; showing ${group.matchingItems.length} matching of ${group.items.length} items; clear the filter to enable collapse` : `${groupExpanded(location.id, group) ? 'Collapse' : 'Expand'} ${group.name}, ${group.items.length} items`" @click="toggleGroup(location, group.key)">
                <img v-if="groupPhoto(group)" :src="itemImage(groupPhoto(group)!)" :alt="`Photo of ${group.name}`" loading="lazy" class="size-14 shrink-0 rounded border bg-background object-contain" @error="failItemImage(groupPhoto(group)!)" />
                <span v-else class="flex size-14 shrink-0 items-center justify-center rounded border text-xs text-muted-foreground" aria-label="No photo">No photo</span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate font-medium">{{ group.name }}</span>
                  <span v-if="group.quantity !== group.items.length" class="block text-xs text-muted-foreground">{{ group.quantity }} units total</span>
                </span>
                <span class="flex shrink-0 items-center gap-1 text-sm text-muted-foreground"><span aria-hidden="true">×{{ searchTerm ? `${group.matchingItems.length}/${group.items.length}` : group.items.length }}</span><span aria-hidden="true">{{ groupExpanded(location.id, group) ? "▾" : "▸" }}</span></span>
              </button>
              <ul v-if="groupExpanded(location.id, group)" class="mt-2 space-y-1 border-l pl-4">
                <li v-for="item in group.matchingItems" :key="item.id" class="flex min-w-0 items-center gap-3 py-2">
                  <img v-if="hasItemImage(item)" :src="itemImage(item)" :alt="`Photo of ${item.name}`" loading="lazy" class="size-12 shrink-0 rounded border bg-background object-contain" @error="failItemImage(item)" />
                  <span v-else class="flex size-12 shrink-0 items-center justify-center rounded border text-xs text-muted-foreground" aria-label="No photo">No photo</span>
                  <div class="min-w-0 flex-1">
                    <NuxtLink :to="`/item/${encodeURIComponent(item.id)}`" class="block truncate hover:underline">{{ item.name }}</NuxtLink>
                    <span v-if="item.archived" class="block text-xs text-muted-foreground">Archived</span>
                    <span v-if="item.displayId" class="block break-all text-xs text-muted-foreground">Generated ID · {{ item.displayId }}</span>
                    <span v-else-if="item.assetId" class="block break-all text-xs text-muted-foreground">Asset ID · {{ item.assetId }}</span>
                    <span v-if="item.serialNumber" class="block break-all text-xs text-muted-foreground">Serial · {{ item.serialNumber }}</span>
                    <span v-if="actionStatusLabel(item.id)" class="block text-xs text-muted-foreground">{{ actionStatusLabel(item.id) }}</span>
                    <span v-if="recentNotes.get(item.id)" class="block truncate text-xs text-muted-foreground">{{ recentNotes.get(item.id) }}</span>
                    <NuxtLink :to="`/location/${encodeURIComponent(location.id)}`" class="block text-xs text-muted-foreground hover:underline">{{ locationPath(location.name) }}</NuxtLink>
                  </div>
                  <span class="shrink-0 text-sm text-muted-foreground">×{{ item.quantity }}</span>
                  <ItemQuickActions :item-id="item.id" compact />
                </li>
              </ul>
            </template>
            <div v-else class="flex min-w-0 items-center gap-3">
              <img v-if="hasItemImage(group.matchingItems[0])" :src="itemImage(group.matchingItems[0])" :alt="`Photo of ${group.matchingItems[0].name}`" loading="lazy" class="size-14 shrink-0 rounded border bg-background object-contain" @error="failItemImage(group.matchingItems[0])" />
              <span v-else class="flex size-14 shrink-0 items-center justify-center rounded border text-xs text-muted-foreground" aria-label="No photo">No photo</span>
              <div class="min-w-0 flex-1">
                <NuxtLink :to="`/item/${encodeURIComponent(group.matchingItems[0].id)}`" class="block truncate hover:underline">{{ group.matchingItems[0].name }}</NuxtLink>
                <span v-if="group.matchingItems[0].archived" class="block text-xs text-muted-foreground">Archived</span>
                <span v-if="group.matchingItems[0].displayId" class="block break-all text-xs text-muted-foreground">Generated ID · {{ group.matchingItems[0].displayId }}</span>
                <span v-else-if="group.matchingItems[0].assetId" class="block break-all text-xs text-muted-foreground">Asset ID · {{ group.matchingItems[0].assetId }}</span>
                <span v-if="group.matchingItems[0].serialNumber" class="block break-all text-xs text-muted-foreground">Serial · {{ group.matchingItems[0].serialNumber }}</span>
                <span v-if="actionStatusLabel(group.matchingItems[0].id)" class="block text-xs text-muted-foreground">{{ actionStatusLabel(group.matchingItems[0].id) }}</span>
                <NuxtLink :to="`/location/${encodeURIComponent(location.id)}`" class="block text-xs text-muted-foreground hover:underline">{{ locationPath(location.name) }}</NuxtLink>
              </div>
              <span class="shrink-0 text-sm text-muted-foreground">×{{ group.matchingItems[0].quantity }}</span>
              <ItemQuickActions :item-id="group.matchingItems[0].id" compact />
            </div>
          </li>
        </ul>

        <ChildContents v-if="!props.directOnly && stateFor(location.id).children.length" :locations="stateFor(location.id).children" :depth="props.depth + 1" :filter="searchTerm" :parent-path="locationPath(location.name)" :loaded-states="states" :hydrator="hydrateChildItems" />
      </div>
    </article>
  </section>
</template>
