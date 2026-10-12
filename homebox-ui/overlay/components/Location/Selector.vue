<template>
  <div class="flex flex-col gap-1">
    <Label :for="id" class="px-1">
      {{ label || "Inside (optional)" }}
    </Label>

    <Popover v-model:open="open">
      <div class="relative">
        <PopoverTrigger as-child>
          <Button :id="id" variant="outline" role="combobox" :aria-expanded="open" class="w-full justify-between">
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
        <Command :ignore-filter="true">
          <CommandInput
            v-model="search"
            @keydown.esc.stop.prevent="open = false"
            :placeholder="'Search locations and items'"
            :display-value="_ => ''"
          />
          <CommandEmpty>{{ loading ? "Loading parents…" : error || "No matching parents" }}</CommandEmpty>
          <CommandList>
            <CommandGroup>
              <CommandItem
                v-for="location in filteredLocations"
                :key="location.id"
                :value="location.id"
                :disabled="loading"
                @select="selectLocation(location as unknown as EntitySummary)"
              >
                <Check :class="cn('mr-2 h-4 w-4', value?.id === location.id ? 'opacity-100' : 'opacity-0')" />
                <div>
                  <div class="flex w-full">
                    {{ location.name }}
                  </div>
                  <div v-if="location.name !== location.treeString" class="mt-1 text-xs text-muted-foreground">
                    {{ location.treeString }}
                  </div>
                </div>
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  </div>
</template>

<script setup lang="ts">
  import { Check, ChevronsUpDown, X } from "lucide-vue-next";
  import fuzzysort from "fuzzysort";
  import { Button } from "~/components/ui/button";
  import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "~/components/ui/command";
  import { Label } from "~/components/ui/label";
  import { Popover, PopoverContent, PopoverTrigger } from "~/components/ui/popover";
  import { cn } from "~/lib/utils";
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
      if (current === revision) rows.value = all;
    } catch (cause) { if (current === revision) error.value = (cause as Error).message; }
    finally { if (current === revision) loading.value = false; }
  }
  watch(open, value => { if (value) void loadParents(); });
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
  const value = useVModel(props, "modelValue", emit);

  function selectLocation(location: EntitySummary) {
    if (value.value?.id !== location.id) {
      value.value = location;
    } else {
      value.value = null;
    }
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
