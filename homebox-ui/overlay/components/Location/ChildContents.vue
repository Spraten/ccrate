<script setup lang="ts">
  import type { EntitySummary } from "~~/lib/api/types/data-contracts";

  type LocationNode = Pick<EntitySummary, "id" | "name" | "itemCount"> & {
    children?: LocationNode[];
  };

  defineOptions({ name: "ChildContents" });
  const props = defineProps<{ locations: LocationNode[] }>();
  const api = useUserApi();
  type PreviewState = { expanded: boolean; loading: boolean; loaded: boolean; items: EntitySummary[]; children: LocationNode[]; error: string };
  const states = reactive(new Map<string, PreviewState>());

  function stateFor(locationId: string) {
    let state = states.get(locationId);
    if (!state) {
      state = { expanded: false, loading: false, loaded: false, items: [], children: [], error: "" };
      states.set(locationId, state);
    }
    return state;
  }

  async function loadItems(locationId: string) {
    const state = stateFor(locationId);
    if (state.loading || state.loaded) return;
    state.loading = true;
    state.error = "";
    try {
      const [response, detail] = await Promise.all([
        api.items.getAll({ parentIds: [locationId] }),
        api.items.getLocation(locationId),
      ]);
      if (response.error || detail.error) throw new Error("request failed");
      state.items = response.data.items;
      state.children = detail.data.children || [];
      state.loaded = true;
    } catch {
      state.error = "Could not load this location's contents. Try again.";
    } finally {
      state.loading = false;
    }
  }

  function toggle(locationId: string) {
    const state = stateFor(locationId);
    state.expanded = !state.expanded;
    if (state.expanded) void loadItems(locationId);
  }

  function retry(locationId: string) {
    const state = stateFor(locationId);
    state.loaded = false;
    void loadItems(locationId);
  }
</script>

<template>
  <section v-if="props.locations.length" class="mt-6 space-y-3" aria-label="Child location contents">
    <h2 class="text-lg font-semibold">Child locations</h2>
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
        <p v-if="stateFor(location.id).loading" role="status" aria-live="polite" class="text-sm text-muted-foreground">Loading items…</p>
        <div v-else-if="stateFor(location.id).error" role="alert" class="flex flex-wrap items-center gap-2 text-sm">
          <span>{{ stateFor(location.id).error }}</span>
          <button type="button" class="underline" @click="retry(location.id)">Retry</button>
        </div>
        <p v-else-if="stateFor(location.id).items.length === 0 && stateFor(location.id).children.length === 0" class="text-sm text-muted-foreground">This location is empty.</p>
        <ul v-else-if="stateFor(location.id).items.length" class="divide-y">
          <li v-for="item in stateFor(location.id).items" :key="item.id" class="flex items-center gap-3 py-2 first:pt-0 last:pb-0">
            <NuxtLink :to="`/item/${encodeURIComponent(item.id)}`" class="min-w-0 flex-1 truncate hover:underline">
              {{ item.name }}
            </NuxtLink>
            <span v-if="item.assetId" class="shrink-0 text-xs text-muted-foreground">{{ item.assetId }}</span>
            <span class="shrink-0 text-sm text-muted-foreground">×{{ item.quantity }}</span>
          </li>
        </ul>

        <ChildContents v-if="stateFor(location.id).children.length" :locations="stateFor(location.id).children" />
      </div>
    </article>
  </section>
</template>
