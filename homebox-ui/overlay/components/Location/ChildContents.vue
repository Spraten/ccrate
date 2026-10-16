<script setup lang="ts">
  import type { EntitySummary } from "~~/lib/api/types/data-contracts";

  type LocationNode = Pick<EntitySummary, "id" | "name" | "itemCount"> & {
    children?: LocationNode[];
  };

  defineOptions({ name: "ChildContents" });
  const props = withDefaults(defineProps<{ locations: LocationNode[]; depth?: number }>(), { depth: 0 });
  const isRoot = props.depth === 0;
  const api = useUserApi();
  type PreviewState = { expanded: boolean; loading: boolean; loaded: boolean; items: EntitySummary[]; children: LocationNode[]; error: string };
  const states = reactive(new Map<string, PreviewState>());
  const directItems = reactive(new Map<string, EntitySummary[]>());
  const loading = ref(false);
  const error = ref("");
  const partial = ref(false);
  const batchLoaded = ref(false);
  const allExpanded = ref(isRoot);

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
      do {
        const response = await api.items.getAll({ parentIds: immediateChildIds, page, pageSize: 100, includeArchived: true });
        if (response.error || !response.data) throw new Error("request failed");
        total = response.data.total;
        for (const item of response.data.items) {
          const parentId = item.parent.id;
          collected.get(parentId)?.push(item);
        }
        if (!response.data.items.length) break;
        page++;
      } while ([...collected.values()].reduce((count, items) => count + items.length, 0) < total);
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
      const detailRequest = api.items.getLocation(locationId);
      const itemRequest = isRoot ? Promise.resolve(null) : api.items.getAll({ parentIds: [locationId] });
      const [detail, items] = await Promise.all([detailRequest, itemRequest]);
      if (detail.error || !detail.data || (items && (items.error || !items.data))) throw new Error("request failed");
      state.children = detail.data.children || [];
      if (items?.data) state.items = items.data.items;
      state.loaded = true;
    } catch {
      state.error = "Could not load this location's details. Try again.";
    } finally {
      state.loading = false;
    }
  }

  function toggle(locationId: string) {
    const state = stateFor(locationId);
    state.expanded = !state.expanded;
    allExpanded.value = props.locations.every(location => stateFor(location.id).expanded);
    if (state.expanded) void loadDetail(locationId);
  }

  function setAllExpanded(expanded: boolean) {
    allExpanded.value = expanded;
    for (const location of props.locations) {
      stateFor(location.id).expanded = expanded;
      if (expanded) void loadDetail(location.id);
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
    for (const location of props.locations) directItems.set(location.id, []);
    void loadItems();
    if (isRoot) {
      for (const location of props.locations) void loadDetail(location.id);
    }
  });
</script>

<template>
  <section v-if="props.locations.length" class="mt-6 space-y-3" aria-label="Child location contents">
    <h2 class="text-lg font-semibold">Child locations</h2>
    <div class="flex flex-wrap gap-3">
      <button type="button" class="text-sm underline" :aria-expanded="allExpanded" @click="setAllExpanded(false)">Collapse all bins</button>
      <button type="button" class="text-sm underline" :aria-expanded="allExpanded" @click="setAllExpanded(true)">Expand bins</button>
    </div>
    <p v-if="loading" role="status" aria-live="polite" class="text-sm text-muted-foreground">Loading bin contents…</p>
    <div v-if="error" role="alert" class="flex flex-wrap items-center gap-2 text-sm">
      <span>{{ error }}</span>
      <button type="button" class="underline" @click="retryBatch">Retry</button>
    </div>
    <article v-for="location in props.locations" :key="location.id" class="overflow-hidden rounded-lg border bg-card">
      <header class="flex flex-wrap items-center gap-2 p-3">
        <button
          type="button"
          class="rounded px-2 py-1 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          :aria-expanded="stateFor(location.id).expanded"
          :aria-label="`${stateFor(location.id).expanded ? 'Collapse' : 'Expand'} contents of ${location.name}`"
          @click="toggle(location.id)"
        >
          <span aria-hidden="true">{{ stateFor(location.id).expanded ? "▾" : "▸" }}</span>
        </button>
        <NuxtLink :to="`/location/${encodeURIComponent(location.id)}`" class="min-w-0 flex-1 font-medium hover:underline">
          {{ location.name }}
        </NuxtLink>
        <span v-if="location.itemCount > 0" class="text-sm text-muted-foreground">{{ location.itemCount }} items</span>
      </header>

      <div v-if="stateFor(location.id).expanded" class="border-t bg-muted/20 p-3 pl-10">
        <p v-if="stateFor(location.id).loading" role="status" aria-live="polite" class="text-sm text-muted-foreground">Loading location details…</p>
        <div v-if="stateFor(location.id).error" role="alert" class="flex flex-wrap items-center gap-2 text-sm">
          <span>{{ stateFor(location.id).error }}</span>
          <button type="button" class="underline" @click="retryDetail(location.id)">Retry</button>
        </div>
        <p v-if="!stateFor(location.id).error && !stateFor(location.id).loading && (isRoot ? directItems.get(location.id)?.length || 0 : stateFor(location.id).items.length) === 0 && stateFor(location.id).children.length === 0 && batchLoaded" class="text-sm text-muted-foreground">This location is empty.</p>
        <ul v-if="(isRoot ? directItems.get(location.id)?.length : stateFor(location.id).items.length)" class="divide-y">
          <li v-for="item in (isRoot ? directItems.get(location.id) : stateFor(location.id).items)" :key="item.id" class="flex min-w-0 items-center gap-3 py-2 first:pt-0 last:pb-0">
            <div class="min-w-0 flex-1">
              <NuxtLink :to="`/item/${encodeURIComponent(item.id)}`" class="block truncate hover:underline">
                {{ item.name }}
              </NuxtLink>
              <span v-if="item.displayId" class="block break-all text-xs text-muted-foreground">Generated ID · {{ item.displayId }}</span>
              <span v-else-if="item.assetId" class="block break-all text-xs text-muted-foreground">{{ item.assetId }}</span>
            </div>
            <span class="shrink-0 text-sm text-muted-foreground">×{{ item.quantity }}</span>
          </li>
        </ul>

        <ChildContents v-if="stateFor(location.id).children.length" :locations="stateFor(location.id).children" :depth="props.depth + 1" />
      </div>
    </article>
  </section>
</template>
