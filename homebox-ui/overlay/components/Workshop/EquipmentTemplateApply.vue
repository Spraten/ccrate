<script setup lang="ts">
import { createEquipmentTemplateApplyFlow } from "~/lib/equipment-catalog";

type NativeItem = { id: string; name: string; entityType?: { id: string } | null; displayId?: string };
type ApplyState = { fields: Record<string, unknown>; selected_fields: string[]; units: { entity_id: string; status: string; error?: string }[] };
const props = defineProps<{ templateId: string; entityTypeId?: string; fields: Record<string, unknown> }>();
const api = useUserApi();
const workshop = useWorkshop();
const { selectedId } = useCollections();
const auth = useAuthContext();
const opened = ref(false);
const loading = ref(false);
const applying = ref(false);
const error = ref("");
const candidates = ref<NativeItem[]>([]);
const reviewedContext = shallowRef<any>(null);
const selectedIds = ref<string[]>([]);
const selectedFields = ref<string[]>(["name", "manufacturer", "modelNumber", "description", "tagIds"]);
const previews = ref<Record<string, any>>({});
const previewing = ref<string[]>([]);
const result = ref<ApplyState | null>(null);
let disposed = false;
const fieldOptions = [
  ["name", "Name"], ["manufacturer", "Manufacturer"], ["modelNumber", "Model"],
  ["description", "Description"], ["tagIds", "Tags"],
] as const;
const statusCounts = computed(() => Object.fromEntries(["succeeded", "failed", "uncertain", "pending"].map(status => [status, result.value?.units.filter(unit => unit.status === status).length || 0])));

function keyFor(groupId: string, userId: string) { return `equipment-template-apply:${groupId}:${userId}:${props.templateId}`; }
function ownerIsCurrent(scope: { identity: string; group_id: string; user_id: string }) {
  const current = workshop.context.value;
  return !disposed && auth.user?.id === scope.user_id && (selectedId.value || auth.user?.defaultGroupId) === scope.group_id &&
    !!current && current.identity === scope.identity && current.group.id === scope.group_id && current.user.id === scope.user_id;
}
function getFlow(context: any) {
  const key = keyFor(context.group.id, context.user.id);
  const scope = { identity: context.identity, group_id: context.group.id, user_id: context.user.id };
  const isCurrent = () => ownerIsCurrent(scope);
  const read = (): ApplyState | null => { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; } };
  const flow = createEquipmentTemplateApplyFlow({
    read,
    write: (state: ApplyState) => { localStorage.setItem(key, JSON.stringify(state)); result.value = state; },
    clear: () => localStorage.removeItem(key),
    getItem: (id: string) => api.items.get(id),
    updateItem: (id: string, update: any) => api.items.update(id, update),
    isCurrent: (expected?: any) => isCurrent() && (!expected || (expected.identity === scope.identity && expected.group_id === scope.group_id && expected.user_id === scope.user_id)),
  });
  result.value = flow.recover();
  return { flow, scope };
}

async function loadCandidates() {
  loading.value = true;
  error.value = "";
  try {
    const context = await workshop.refresh();
    const scope = { identity: context.identity, group_id: context.group.id, user_id: context.user.id };
    const stillCurrent = () => ownerIsCurrent(scope);
    const matches: NativeItem[] = [];
    let page = 1;
    let total = 0;
    do {
      const response = await api.items.getAll({ page, pageSize: 100, includeArchived: false });
      if (!stillCurrent()) throw new Error("The account or collection changed while items were loading.");
      if (response.error || !response.data) throw response.error || new Error("Items could not be loaded.");
      total = response.data.total;
      matches.push(...response.data.items.filter((item: NativeItem) => item.entityType?.id === props.entityTypeId));
      if (!response.data.items.length) break;
      page++;
    } while (matches.length < total && page < 1000);
    if (!stillCurrent()) throw new Error("The account or collection changed while items were loading.");
    reviewedContext.value = context;
    candidates.value = matches;
    selectedIds.value = [];
    previews.value = {};
    const { flow } = getFlow(context);
    result.value = flow.pending();
  } catch (cause) { error.value = (cause as Error).message || "Items could not be loaded."; }
  finally { loading.value = false; }
}

async function toggleItem(id: string, checked: boolean) {
  selectedIds.value = checked ? [...new Set([...selectedIds.value, id])] : selectedIds.value.filter(value => value !== id);
  if (!checked) { delete previews.value[id]; return; }
  previewing.value = [...new Set([...previewing.value, id])];
  try {
    const response = await api.items.get(id);
    if (response.error || !response.data || response.data.id !== id) {
      error.value = `Could not revalidate ${id}; it cannot be selected.`;
      selectedIds.value = selectedIds.value.filter(value => value !== id);
      return;
    }
    previews.value[id] = response.data;
  } finally {
    previewing.value = previewing.value.filter(value => value !== id);
  }
}

function previewValue(field: string, value: any) {
  if (field === "tagIds") return Array.isArray(value) ? value.map((tag: any) => tag.name || tag).join(", ") || "None" : "None";
  return String(value || "—");
}

async function apply() {
  applying.value = true;
  error.value = "";
  try {
    const context = reviewedContext.value;
    if (!context) throw new Error("Reload the item list before applying this template.");
    const { flow, scope } = getFlow(context);
    if (!ownerIsCurrent(scope)) throw new Error("The account or collection changed; reload the item list before applying.");
    result.value = await flow.apply({ selectedEntityIds: selectedIds.value, selectedFields: selectedFields.value, fields: props.fields, scope });
  } catch (cause) { error.value = (cause as Error).message || "The template could not be applied."; }
  finally { applying.value = false; }
}

async function reconcile(entityId: string, updated: boolean) {
  try {
    const context = reviewedContext.value;
    if (!context) throw new Error("Reload the item list before reconciling this result.");
    const { flow } = getFlow(context);
    result.value = flow.resolveUncertain(entityId, updated ? "succeeded" : "failed");
  } catch (cause) { error.value = (cause as Error).message || "The item result could not be reconciled."; }
}

watch(opened, value => { if (value) void loadCandidates(); });
watch([selectedId, () => auth.user?.id], () => {
  reviewedContext.value = null;
  selectedIds.value = [];
  previews.value = {};
}, { flush: "sync" });
onBeforeUnmount(() => { disposed = true; });
</script>

<template>
  <div class="mt-2">
    <Button type="button" variant="outline" size="sm" @click="opened = !opened">{{ opened ? "Close unit apply" : "Apply to existing items" }}</Button>
    <section v-if="opened" class="mt-2 space-y-3 rounded-md border p-3" aria-label="Apply template to selected items">
      <p class="text-sm">Choose the exact items and shared fields to update. Each item is shown with its current and proposed values before confirmation.</p>
      <p v-if="loading" role="status">Loading items…</p>
      <fieldset v-else class="max-h-48 space-y-1 overflow-auto rounded border p-2">
        <legend class="px-1 text-sm font-medium">Native items in this collection</legend>
        <label v-for="item in candidates" :key="item.id" class="flex items-center gap-2 text-sm">
          <input type="checkbox" :checked="selectedIds.includes(item.id)" @change="toggleItem(item.id, ($event.target as HTMLInputElement).checked)" />
          <span>{{ item.name }} · {{ item.displayId || item.id }}</span>
        </label>
        <p v-if="!candidates.length" class="text-sm text-muted-foreground">No active items of this equipment type were found.</p>
      </fieldset>
      <fieldset class="flex flex-wrap gap-3">
        <legend class="mb-1 w-full text-sm font-medium">Shared fields</legend>
        <label v-for="[field, label] in fieldOptions" :key="field" class="flex items-center gap-2 text-sm">
          <input v-model="selectedFields" type="checkbox" :value="field" />{{ label }}
        </label>
      </fieldset>
      <div v-if="selectedIds.length" class="max-h-64 space-y-2 overflow-auto rounded border p-2">
        <h4 class="text-sm font-medium">Preview · {{ selectedIds.length }} selected</h4>
        <article v-for="id in selectedIds" :key="id" class="border-t py-2 text-xs">
          <p class="mb-1 font-medium">{{ previews[id]?.name || id }} · {{ id }}</p>
          <p v-for="field in selectedFields" :key="field">
            {{ field }}: {{ previewValue(field, previews[id]?.[field] ?? (field === "tagIds" ? previews[id]?.tags : "")) }} →
            {{ previewValue(field, fields[field]) }}
          </p>
        </article>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Button type="button" :disabled="applying || loading || !selectedIds.length || !selectedFields.length || selectedIds.some(id => !previews[id] || previewing.includes(id)) || result?.units.some(unit => unit.status === 'uncertain' || unit.status === 'in_flight')" @click="apply">
          {{ applying ? "Applying…" : "Confirm and apply" }}
        </Button>
        <span v-if="result" class="text-xs" role="status">{{ statusCounts.succeeded }} succeeded · {{ statusCounts.failed }} failed · {{ statusCounts.uncertain }} need review</span>
      </div>
      <p v-if="result?.units.some(unit => unit.status === 'uncertain')" class="text-sm text-amber-700">An update may have reached Homebox. It will not be repeated automatically. Check the listed item before applying again.</p>
      <ul v-if="result" class="space-y-1 text-xs">
        <li v-for="unit in result.units" :key="unit.entity_id">
          {{ unit.entity_id }}: {{ unit.status }}<span v-if="unit.error"> · {{ unit.error }}</span>
          <template v-if="unit.status === 'uncertain'">
            <Button type="button" size="sm" variant="outline" class="ml-2" @click="reconcile(unit.entity_id, true)">Confirm updated</Button>
            <Button type="button" size="sm" variant="outline" class="ml-1" @click="reconcile(unit.entity_id, false)">Confirm not updated</Button>
          </template>
        </li>
      </ul>
      <p v-if="error" class="text-sm text-destructive" role="alert">{{ error }}</p>
    </section>
  </div>
</template>
