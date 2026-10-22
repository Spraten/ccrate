<script setup lang="ts">
import { PACKAGING_OPTIONS, validateCustomRows } from "~/lib/item-create-fields";
import { changeRelatedItem, detailMetadataDraft, saveDetailMetadata, searchRelatedItems } from "~/lib/item-metadata";
import { workshopUUID } from "~/lib/workshop-uuid";

type NativeItem = { id: string; name?: string; serialNumber?: string; fields?: any[] };
type RelatedItem = { id?: string; name?: string; unavailable?: boolean };
const props = defineProps<{ item: NativeItem }>();
const emit = defineEmits<{ changed: [] }>();
const api = useUserApi();
const workshop = useWorkshop();
const { selectedId } = useCollections();
const auth = useAuthContext();
const draft = ref({ serialNumber: "", packaging: "", rows: [] as { name: string; value: string; note: string }[] });
const baselineItem = ref<NativeItem | null>(null);
const related = ref<RelatedItem[]>([]);
const loading = ref(false), ready = ref(false), saving = ref(false), linking = ref(false), searching = ref(false);
const error = ref(""), message = ref(""), searchError = ref("");
const query = ref(""), candidates = ref<{ id: string; name: string }[]>([]), chosenId = ref("");
const pendingSave = ref<{ requestKey: string; identity: string; draft: typeof draft.value } | null>(null);
const pendingRelation = ref<{ action: "add" | "remove"; relatedId: string; requestKey: string; identity: string } | null>(null);
const baselineNotes = ref<Record<string, string>>({});
let revision = 0, searchRevision = 0;

async function load() {
  const own = ++revision;
  const nativeBaseline = JSON.parse(JSON.stringify(props.item)) as NativeItem;
  loading.value = true; ready.value = false; error.value = "";
  try {
    const result = await workshop.request<any>(`item-metadata?entity_id=${encodeURIComponent(props.item.id)}`);
    if (own !== revision) return;
    related.value = Array.isArray(result.relatedItems) ? result.relatedItems : [];
    baselineNotes.value = result.fieldNotes || {};
    if (!pendingSave.value) { baselineItem.value = nativeBaseline; draft.value = detailMetadataDraft(nativeBaseline, result); }
    ready.value = true;
  } catch (cause) { if (own === revision) error.value = (cause as Error).message || "Item metadata could not be loaded."; }
  finally { if (own === revision) loading.value = false; }
}

async function save() {
  if (saving.value || loading.value || !ready.value) return;
  saving.value = true; error.value = ""; message.value = "";
  try {
    const context = await workshop.refresh();
    if (!context?.group?.id || !context?.user?.id || !context.identity) throw new Error("Refresh the account and collection before saving.");
    if (pendingSave.value && pendingSave.value.identity !== context.identity) throw new Error("The account or collection changed. Return to the original context to retry.");
    if (!pendingSave.value) {
      validateCustomRows(draft.value.rows);
      pendingSave.value = { requestKey: workshopUUID(), identity: context.identity, draft: {
        serialNumber: draft.value.serialNumber, packaging: draft.value.packaging, rows: draft.value.rows.map(row => ({ ...row })),
      } };
    }
    const saved = await saveDetailMetadata({ api, workshop, item: baselineItem.value || props.item, draft: pendingSave.value.draft, identity: pendingSave.value.identity, requestKey: pendingSave.value.requestKey, baselineNotes: baselineNotes.value });
    pendingSave.value = null;
    draft.value = detailMetadataDraft(saved.item, { fieldNotes: saved.fieldNotes });
    baselineItem.value = JSON.parse(JSON.stringify(saved.item)) as NativeItem;
    baselineNotes.value = saved.fieldNotes;
    message.value = "Packaging and custom fields saved.";
    emit("changed");
  } catch (cause) {
    const status = Number((cause as any)?.status || (cause as any)?.statusCode || (cause as any)?.response?.status || 0);
    if (status >= 400 && status < 500 && ![408, 409, 429].includes(status)) pendingSave.value = null;
    error.value = (cause as Error).message || "Metadata could not be saved. Retry the same request.";
  }
  finally { saving.value = false; }
}

async function search() {
  if (!ready.value) return;
  const own = ++searchRevision;
  chosenId.value = ""; searchError.value = "";
  if (!query.value.trim()) { candidates.value = []; return; }
  searching.value = true;
  try {
    const found = await searchRelatedItems(api, query.value, props.item.id);
    if (own === searchRevision) candidates.value = found;
  } catch (cause) { if (own === searchRevision) searchError.value = (cause as Error).message || "Items could not be searched."; }
  finally { if (own === searchRevision) searching.value = false; }
}

async function changeRelation(action: "add" | "remove", relatedId: string) {
  if (linking.value || !ready.value || !relatedId) return;
  linking.value = true; error.value = ""; message.value = "";
  try {
    const context = await workshop.refresh();
    if (!context?.group?.id || !context?.user?.id || !context.identity) throw new Error("Refresh the account and collection before changing links.");
    const pending = pendingRelation.value;
    if (pending && (pending.action !== action || pending.relatedId !== relatedId || pending.identity !== context.identity)) throw new Error("Retry the pending related item change first.");
    pendingRelation.value ||= { action, relatedId, requestKey: workshopUUID(), identity: context.identity };
    const result = await changeRelatedItem(workshop, props.item.id, relatedId, action, pendingRelation.value.requestKey, context.identity);
    pendingRelation.value = null;
    chosenId.value = ""; query.value = ""; candidates.value = [];
    related.value = result.relatedItems;
    message.value = action === "add" ? "Related item linked." : "Related item removed.";
  } catch (cause) {
    const status = Number((cause as any)?.status || (cause as any)?.statusCode || (cause as any)?.response?.status || 0);
    if (status >= 400 && status < 500 && ![408, 409, 429].includes(status)) pendingRelation.value = null;
    error.value = (cause as Error).message || "Related item change could not be confirmed. Retry the same request.";
  }
  finally { linking.value = false; }
}

watch(() => props.item.id, () => { revision++; searchRevision++; ready.value = false; baselineItem.value = null; baselineNotes.value = {}; pendingSave.value = null; pendingRelation.value = null; related.value = []; void load(); });
watch([selectedId, () => auth.user?.id], () => { revision++; searchRevision++; ready.value = false; baselineItem.value = null; baselineNotes.value = {}; pendingSave.value = null; pendingRelation.value = null; related.value = []; candidates.value = []; void load(); });
onMounted(load);
</script>

<template>
  <details class="rounded-md border p-4" :open="!!error" aria-label="Packaging, custom fields and related items">
    <summary class="cursor-pointer text-base font-semibold">Packaging, custom fields and related items <span v-if="loading" class="ml-2 text-sm font-normal text-muted-foreground">Loading…</span></summary>
    <div class="mt-4 space-y-4">
    <p v-if="loading" role="status" class="text-sm">Loading item metadata…</p>
    <button v-if="!ready && !loading" type="button" class="rounded border px-3 py-1 text-sm" @click="load">Retry metadata load</button>
    <div v-if="!loading" class="space-y-3">
      <label class="block text-sm font-medium">Manufacturer serial number
        <input v-model="draft.serialNumber" :disabled="!ready || saving || !!pendingSave" class="mt-1 block w-full rounded border bg-background px-2 py-1" />
      </label>
      <label class="block text-sm font-medium">Device Packaging
        <select v-model="draft.packaging" :disabled="!ready || saving || !!pendingSave" class="mt-1 block w-full rounded border bg-background px-2 py-1">
          <option value="">Unspecified</option>
          <option v-for="option in PACKAGING_OPTIONS" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <div v-for="(row, index) in draft.rows" :key="index" class="grid gap-2 rounded border p-2 sm:grid-cols-3">
        <label class="text-sm">Custom field name<input v-model="row.name" :disabled="!ready || saving || !!pendingSave" class="mt-1 block w-full rounded border bg-background px-2 py-1" /></label>
        <label class="text-sm">Custom field value<input v-model="row.value" :disabled="!ready || saving || !!pendingSave" class="mt-1 block w-full rounded border bg-background px-2 py-1" /></label>
        <label class="text-sm">Custom field note<input v-model="row.note" :disabled="!ready || saving || !!pendingSave" class="mt-1 block w-full rounded border bg-background px-2 py-1" /></label>
        <button type="button" class="text-sm underline" :disabled="!ready || saving || !!pendingSave" @click="draft.rows.splice(index, 1)">Remove field</button>
      </div>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="rounded border px-3 py-1 text-sm" :disabled="!ready || saving || !!pendingSave" @click="draft.rows.push({ name: '', value: '', note: '' })">Add field</button>
        <button type="button" class="rounded border px-3 py-1 text-sm font-medium" :disabled="!ready || saving" @click="save">{{ saving ? 'Saving…' : pendingSave ? 'Retry metadata save' : 'Save fields' }}</button>
      </div>
      <div class="border-t pt-3 space-y-2">
        <h3 class="text-sm font-semibold">Related items</h3>
        <p v-if="!related.length" class="text-sm text-muted-foreground">No related items.</p>
        <div v-for="(link, index) in related" :key="link.id || `unavailable-${index}`" class="flex items-center justify-between gap-3 text-sm">
          <span v-if="link.unavailable || !link.id" class="text-muted-foreground">Unavailable item</span>
          <NuxtLink v-else :to="`/item/${link.id}`" class="underline">{{ link.name || link.id }}</NuxtLink>
          <button v-if="link.id && !link.unavailable" type="button" class="underline" :disabled="!ready || linking" @click="changeRelation('remove', link.id)">Remove link</button>
        </div>
        <label class="block text-sm">Find an existing item
          <input v-model="query" :disabled="!ready || linking" class="mt-1 block w-full rounded border bg-background px-2 py-1" @input="search" />
        </label>
        <p v-if="searching" class="text-sm">Searching…</p>
        <p v-if="searchError" role="alert" class="text-sm text-destructive">{{ searchError }}</p>
        <label v-if="candidates.length" class="block text-sm">Search results
          <select v-model="chosenId" :disabled="!ready || linking" class="mt-1 block w-full rounded border bg-background px-2 py-1">
            <option value="">Choose an item</option>
            <option v-for="candidate in candidates" :key="candidate.id" :value="candidate.id">{{ candidate.name }}</option>
          </select>
        </label>
        <button type="button" class="rounded border px-3 py-1 text-sm" :disabled="!ready || linking || !chosenId" @click="changeRelation('add', chosenId)">Link existing item</button>
      </div>
    </div>
    <p v-if="message" role="status" class="text-sm">{{ message }}</p>
    <p v-if="error" role="alert" class="text-sm text-destructive">{{ error }}</p>
    </div>
  </details>
</template>
