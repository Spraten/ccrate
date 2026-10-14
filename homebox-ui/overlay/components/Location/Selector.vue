<template>
  <div class="flex flex-col gap-1">
    <Label :for="id" class="px-1">
      {{ label || "Inside (optional)" }}
    </Label>

    <Popover v-model:open="open">
      <div class="relative">
        <PopoverTrigger as-child>
          <Button :id="id" variant="outline" aria-haspopup="dialog" :aria-expanded="open" class="w-full justify-between">
            <span class="min-w-0 flex-auto truncate text-left" :class="value ? 'pr-8' : ''">
              {{ value && value.name ? value.name : "Top level / no parent" }}
            </span>
            <ChevronsUpDown class="ml-2 size-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <button
          v-if="value"
          type="button"
          class="absolute right-8 top-1/2 -translate-y-1/2 rounded p-1 hover:bg-primary/20"
          :aria-label="$t('components.location.selector.clear')"
          @click="clearSelection"
        >
          <X class="size-4" />
        </button>
      </div>
      <PopoverContent class="w-[--reka-popper-anchor-width] p-0">
        <input
          :value="search"
          type="search"
          aria-label="Search locations and items"
          class="w-full border-b bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
          placeholder="Search locations and items"
          @input="search = ($event.target as HTMLInputElement).value"
          @keydown.esc.stop.prevent="open = false"
        />
        <div v-if="!search.trim()" role="group" aria-label="Locations" class="max-h-72 overflow-y-auto p-1">
            <button
              type="button"
              class="w-full rounded-sm px-3 py-2 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              @click.stop="selectNoParent"
            >
              Top level / no parent
            </button>
            <div v-for="location in visibleLocations" :key="location.id" class="flex min-w-0 items-center rounded-sm pr-2 hover:bg-accent" :style="{ paddingLeft: `${location.depth * 1.25}rem` }">
              <button
                v-if="hasChildren(location)"
                type="button"
                class="flex size-8 shrink-0 items-center justify-center rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                :aria-label="`${isExpanded(location) ? 'Collapse' : 'Expand'} ${location.name}`"
                :aria-expanded="isExpanded(location)"
                @click.stop="toggleExpanded(location)"
              >
                <ChevronsDown v-if="isExpanded(location)" class="size-4" aria-hidden="true" />
                <ChevronRight v-else class="size-4" aria-hidden="true" />
              </button>
              <span v-else class="w-8 shrink-0" aria-hidden="true" />
              <button
                type="button"
                class="min-w-0 flex-1 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                :aria-current="value?.id === location.id ? 'true' : undefined"
                @click.stop="selectLocation(location as unknown as EntitySummary)"
              >
                <span class="block truncate">{{ location.name }}</span>
              </button>
            </div>
            <div v-if="!loading && !error && !visibleLocations.length" class="px-3 py-2 text-sm text-muted-foreground">No locations</div>
            <div v-if="loading || error" class="px-3 py-2 text-sm text-muted-foreground" role="status">
              {{ loading ? "Loading parents…" : error }}
            </div>
          </div>
        <div v-else-if="!loading && !error && filteredLocations.length" role="group" aria-label="Matching locations" class="max-h-72 overflow-y-auto p-1">
          <button
            v-for="location in filteredLocations"
            :key="location.id"
            type="button"
            class="flex w-full items-start rounded-sm px-3 py-2 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            @click="selectLocation(location as unknown as EntitySummary)"
          >
            <span class="min-w-0">
              <span class="block truncate">{{ location.name }}</span>
              <span v-if="location.name !== location.treeString" class="mt-1 block truncate text-xs text-muted-foreground">{{ location.treeString }}</span>
            </span>
          </button>
        </div>
        <div v-else class="px-3 py-2 text-sm text-muted-foreground" role="status">
          {{ loading ? "Loading parents…" : error || "No matching parents" }}
        </div>
      </PopoverContent>
    </Popover>
  </div>
</template>

<script setup lang="ts">
  import { ChevronsDown, ChevronsUpDown, ChevronRight, X } from "lucide-vue-next";
  import fuzzysort from "fuzzysort";
  import { Button } from "~/components/ui/button";
  import { Label } from "~/components/ui/label";
  import { Popover, PopoverContent, PopoverTrigger } from "~/components/ui/popover";
  import type { EntitySummary } from "~~/lib/api/types/data-contracts";

  type Props = {
    modelValue?: EntitySummary | null;
    currentLocation?: EntitySummary;
    excludeIds?: string[];
    label?: string;
  };

  const props = defineProps<Props>();
  const emit = defineEmits(["update:modelValue"]);

  const open = ref(false);
  const search = ref("");
  const id = useId();
  const api = useUserApi();
  const { selectedId } = useCollections();
  const rows = ref<EntitySummary[]>([]), loading = ref(false), error = ref("");
  const expandedIds = ref(new Set<string>());
  let revision = 0;
  async function loadParents() {
    const current = ++revision;
    rows.value = []; loading.value = true; error.value = "";
    try {
      const all: EntitySummary[] = [];
      for (const isLocation of [true, false]) {
        let page = 1, count = 0;
        while (true) {
          const result = await api.items.getAll({ isLocation, includeArchived: true, page, pageSize: 100 });
          if (current !== revision) return;
          if (result.error || !result.data) throw Error("Could not load parents. Close and reopen the selector to try again.");
          all.push(...result.data.items); count += result.data.items.length;
          if (count >= result.data.total || !result.data.items.length) break;
          page++;
        }
      }
      if (current === revision) {
        rows.value = all;
        expandSelectedPath();
      }
    } catch (cause) { if (current === revision) error.value = (cause as Error).message; }
    finally { if (current === revision) loading.value = false; }
  }
  watch(open, value => {
    if (value) {
      search.value = "";
      void loadParents();
    }
  });
  watch([selectedId, () => useAuthContext().user?.id], () => {
    revision++; rows.value = []; error.value = ""; loading.value = false;
    if (open.value) void loadParents();
  });
  onBeforeUnmount(() => { revision++; });
  const locations = computed(() => {
    const byId = new Map(rows.value.map(row => [row.id, row]));
    const excluded = new Set([...(props.excludeIds || []), ...(props.currentLocation ? [props.currentLocation.id] : [])]);
    return rows.value.filter(row => {
      if (row.archived) return false;
      const seen = new Set<string>();
      let current: EntitySummary | undefined = row;
      while (current) {
        if (excluded.has(current.id) || seen.has(current.id)) return false;
        seen.add(current.id); current = current.parent?.id ? byId.get(current.parent.id) : undefined;
      }
      return true;
    }).map(row => {
      const path: string[] = [], seen = new Set<string>();
      let current: EntitySummary | undefined = row;
      while (current && !seen.has(current.id)) {
        seen.add(current.id); path.unshift(current.name);
        current = current.parent?.id ? byId.get(current.parent.id) : undefined;
      }
      return { ...row, treeString: path.join(" / ") };
    });
  });
  const visibleLocations = computed(() => {
    const byId = new Map(locations.value.map(location => [location.id, location]));
    const children = new Map<string, typeof locations.value>();
    const roots: typeof locations.value = [];
    for (const location of locations.value) {
      const parentId = location.parent?.id;
      if (parentId && byId.has(parentId)) {
        const siblings = children.get(parentId) || [];
        siblings.push(location);
        children.set(parentId, siblings);
      } else roots.push(location);
    }

    const visible: Array<(typeof locations.value)[number] & { depth: number }> = [];
    const append = (location: (typeof locations.value)[number], depth: number) => {
      visible.push({ ...location, depth });
      if (expandedIds.value.has(location.id)) {
        for (const child of children.get(location.id) || []) append(child, depth + 1);
      }
    };
    for (const root of roots) append(root, 0);
    return visible;
  });
  const value = useVModel(props, "modelValue", emit);

  function hasChildren(location: EntitySummary) {
    return locations.value.some(candidate => candidate.parent?.id === location.id);
  }

  function isExpanded(location: EntitySummary) {
    return expandedIds.value.has(location.id);
  }

  function toggleExpanded(location: EntitySummary) {
    const next = new Set(expandedIds.value);
    if (next.has(location.id)) next.delete(location.id);
    else next.add(location.id);
    expandedIds.value = next;
  }

  function expandSelectedPath() {
    if (!value.value) return;
    const byId = new Map(locations.value.map(location => [location.id, location]));
    const next = new Set(expandedIds.value);
    let current = byId.get(value.value.id);
    while (current?.parent?.id && byId.has(current.parent.id)) {
      next.add(current.parent.id);
      current = byId.get(current.parent.id);
    }
    expandedIds.value = next;
  }

  watch(() => value.value?.id, () => {
    if (open.value) expandSelectedPath();
  });

  function selectLocation(location: EntitySummary) {
    if (value.value?.id !== location.id) {
      value.value = location;
    } else {
      value.value = null;
    }
    open.value = false;
  }

  function selectNoParent() {
    value.value = null;
    search.value = "";
    open.value = false;
  }

  function clearSelection() {
    value.value = null;
    search.value = "";
    open.value = false;
  }

  const filteredLocations = computed(() => {
    const filtered = fuzzysort.go(search.value, locations.value, { key: "treeString", all: true }).map(i => i.obj);

    return filtered;
  });

  // Reset search when value is cleared
  watch(
    () => value.value,
    () => {
      if (!value.value) {
        search.value = "";
      }
    }
  );
</script>
