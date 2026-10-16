<script setup lang="ts">
  import type { EntitySummary } from "~~/lib/api/types/data-contracts";

  type LocationNode = Pick<EntitySummary, "id" | "name" | "itemCount"> & {
    children?: LocationNode[];
  };

  defineOptions({ name: "ChildContents" });
  type PreviewState = { expanded: boolean; loading: boolean; loaded: boolean; items: EntitySummary[]; children: LocationNode[]; error: string };
  const props = withDefaults(defineProps<{ locations: LocationNode[]; depth?: number; filter?: string; parentPath?: string; loadedStates?: Map<string, PreviewState> }>(), { depth: 0, filter: "", parentPath: "" });
  const isRoot = props.depth === 0;
  const api = useUserApi();
  const states = props.loadedStates ?? reactive(new Map<string, PreviewState>());
  const directItems = reactive(new Map<string, EntitySummary[]>());
  const loading = ref(false);
  const error = ref("");
  const partial = ref(false);
  const batchLoaded = ref(false);
  const allExpanded = ref(isRoot);
  const filterText = ref("");
  const searchTerm = computed(() => (isRoot ? filterText.value : props.filter).trim().toLocaleLowerCase());

  function itemsFor(location: LocationNode, nested = false): EntitySummary[] {
    return isRoot && !nested ? (directItems.get(location.id) || []) : stateFor(location.id).items;
  }

  function matchesItem(item: EntitySummary) {
    const term = searchTerm.value;
    return !term || [item.name, item.displayId, item.assetId, item.manufacturer, item.modelNumber, item.serialNumber]
      .some(value => String(value || "").toLocaleLowerCase().includes(term));
  }

  function visibleItems(location: LocationNode) {
    return itemsFor(location).filter(matchesItem);
  }

  function matchesLocationName(location: LocationNode) {
    return Boolean(searchTerm.value) && location.name.toLocaleLowerCase().includes(searchTerm.value);
  }

  function hasLoadedMatch(location: LocationNode, nested = false) {
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
          const parentId = item.parent.id;
          collected.get(parentId)?.push(item);
        }
        if (!response.data.items.length) break;
        page++;
      } while (received < total);
      for (const [id, items] of collected) directItems.set(id, items);
      batchLoaded.value = true;
    } catch {
      for (const [id, items] of collected) directItems.set(id, items);
      partial.value = [...collected.values()].some(items => items.length > 0);
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
      const detail = await api.items.getLocation(locationId);
      if (detail.error || !detail.data) throw new Error("request failed");
      state.children = detail.data.children || [];
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
          state.items = collected.slice();
          page++;
        } while (received < total);
      }
      state.loaded = true;
    } catch {
      state.error = state.items.length
        ? "Some location contents could not be loaded. Results may be incomplete."
        : "Could not load this location's details. Try again.";
    } finally {
      state.loading = false;
    }
  }

  function toggle(locationId: string) {
    const state = stateFor(locationId);
    state.expanded = !state.expanded;
    allExpanded.value = props.locations.every(location => stateFor(location.id).expanded);
    if (state.expanded && !isRoot) void loadDetail(locationId);
    else if (state.expanded && state.loaded === false) void loadDetail(locationId);
  }

  function setAllExpanded(expanded: boolean) {
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
  <section v-if="props.locations.length" class="mt-6 space-y-3" aria-label="Child location contents">
    <h2 class="text-lg font-semibold">Child locations</h2>
    <div v-if="isRoot" class="flex flex-wrap items-center gap-2">
      <label class="sr-only" for="cabinet-contents-filter">Filter loaded cabinet contents</label>
      <input id="cabinet-contents-filter" v-model="filterText" type="search" aria-label="Filter loaded cabinet contents" placeholder="Filter loaded contents" class="min-w-0 flex-1 rounded border bg-background px-3 py-2 text-sm" />
      <button v-if="filterText" type="button" class="text-sm underline" @click="filterText = ''">Clear filter</button>
      <p class="basis-full text-xs text-muted-foreground">Search covers loaded cabinet contents only; expand bins to load deeper locations.</p>
    </div>
    <div class="flex flex-wrap gap-3">
      <button type="button" class="text-sm underline" :aria-expanded="allExpanded" @click="setAllExpanded(false)">Collapse all bins</button>
      <button type="button" class="text-sm underline" :aria-expanded="allExpanded" @click="setAllExpanded(true)">Expand bins</button>
    </div>
    <p v-if="loading" role="status" aria-live="polite" class="text-sm text-muted-foreground">Loading bin contents…</p>
    <div v-if="error" role="alert" class="flex flex-wrap items-center gap-2 text-sm">
      <span>{{ error }}</span>
      <button type="button" class="underline" @click="retryBatch">Retry</button>
    </div>
    <p v-if="searchTerm && filteredLocations().length === 0" role="status" class="text-sm text-muted-foreground">No loaded locations match this filter.</p>
    <article v-for="location in filteredLocations()" :key="location.id" class="overflow-hidden rounded-lg border bg-card">
      <header class="flex flex-wrap items-center gap-2 p-3">
        <button
          type="button"
          class="rounded px-2 py-1 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          :aria-expanded="isExpandedForDisplay(location)"
          :aria-label="`${isExpandedForDisplay(location) ? 'Collapse' : 'Expand'} contents of ${location.name}`"
          @click="toggle(location.id)"
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
        <p v-if="!stateFor(location.id).error && !stateFor(location.id).loading && itemsFor(location).length === 0 && stateFor(location.id).children.length === 0 && (isRoot ? batchLoaded : stateFor(location.id).loaded)" class="text-sm text-muted-foreground">This location is empty.</p>
        <ul v-if="visibleItems(location).length" class="divide-y">
          <li v-for="item in visibleItems(location)" :key="item.id" class="flex min-w-0 items-center gap-3 py-2 first:pt-0 last:pb-0">
            <div class="min-w-0 flex-1">
              <NuxtLink :to="`/item/${encodeURIComponent(item.id)}`" class="block truncate hover:underline">
                {{ item.name }}
              </NuxtLink>
              <span v-if="item.archived" class="block text-xs text-muted-foreground">Archived</span>
              <span v-if="item.displayId" class="block break-all text-xs text-muted-foreground">Generated ID · {{ item.displayId }}</span>
              <span v-else-if="item.assetId" class="block break-all text-xs text-muted-foreground">{{ item.assetId }}</span>
              <NuxtLink :to="`/location/${encodeURIComponent(location.id)}`" class="block text-xs text-muted-foreground hover:underline">{{ locationPath(location.name) }}</NuxtLink>
            </div>
            <span class="shrink-0 text-sm text-muted-foreground">×{{ item.quantity }}</span>
          </li>
        </ul>

        <ChildContents v-if="stateFor(location.id).children.length" :locations="stateFor(location.id).children" :depth="props.depth + 1" :filter="searchTerm" :parent-path="locationPath(location.name)" :loaded-states="states" />
      </div>
    </article>
  </section>
</template>
