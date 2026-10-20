<script setup lang="ts">
import { createEquipmentTemplateLifecycleFlow, createEquipmentTemplateSaveFlow, equipmentTemplatePhotoFallback, equipmentTemplateSaveStorageKey, listEquipmentTemplates, saveEquipmentTemplate } from "~/lib/equipment-catalog";
import EquipmentTemplateApply from "~/components/Workshop/EquipmentTemplateApply.vue";

type EquipmentTemplate = {
  id: string;
  name: string;
  entity_type_id: string;
  manufacturer: string;
  model_number: string;
  model_code: string;
  description: string;
  tag_ids: string[];
  photo_attachment_id?: string;
  photo_entity_id?: string;
  updated_at?: string;
  archived?: boolean;
};
type PhotoSource = { id: string; name: string; displayId?: string; entityType?: { id: string } | null; };

const props = defineProps<{
  entityTypeId?: string;
  fields: Record<string, unknown>;
  modelValue: string | null;
  hasItemPhoto?: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [id: string | null];
  apply: [template: EquipmentTemplate];
}>();
const workshop = useWorkshop();
const templates = ref<EquipmentTemplate[]>([]);
const loading = ref(false);
const saving = ref(false);
const message = ref("");
const error = ref("");
const available = computed(() => templates.value.filter(item => item.entity_type_id === props.entityTypeId && !item.archived));
const selectedTemplate = computed(() => available.value.find(item => item.id === props.modelValue) || null);
const archivedTemplates = computed(() => templates.value.filter(item => item.entity_type_id === props.entityTypeId && item.archived));
const showArchived = ref(false);
const pendingLifecycle = ref<any>(null);
const editing = ref(false);
const workshopApi = useUserApi();
const api = useUserApi();
const photoSources = ref<PhotoSource[]>([]);
const photoSourceId = ref("");
const pendingSave = ref<any>(null);
const latestConflictTemplate = ref<EquipmentTemplate | null>(null);
const staleReviewConfirmed = ref(false);
let saveFlowKey = "";
let saveFlow: ReturnType<typeof createEquipmentTemplateSaveFlow> | null = null;
const { selectedId: selectedCollectionId } = useCollections();
const auth = useAuthContext();

function templatePhotoUrl(item: EquipmentTemplate | null) {
  const photo = equipmentTemplatePhotoFallback(item, props.hasItemPhoto);
  return photo ? workshopApi.authURL(`/entities/${photo.entity_id}/attachments/${photo.attachment_id}`) : "";
}

async function refresh() {
  if (!props.entityTypeId) { templates.value = []; return; }
  loading.value = true;
  error.value = "";
  try {
    templates.value = await listEquipmentTemplates(workshop, true) as EquipmentTemplate[];
    photoSources.value = await loadPhotoSources();
    const context = await workshop.refresh();
    await bindSaveFlow(context);
    lifecycleFlow(context);
    if (props.modelValue && !templates.value.some(item => item.id === props.modelValue && !item.archived)) emit("update:modelValue", null);
  } catch (cause) {
    error.value = (cause as Error).message || "Equipment templates could not be loaded.";
  } finally { loading.value = false; }
}

async function bindSaveFlow(context: any) {
  const key = equipmentTemplateSaveStorageKey(context);
  if (!saveFlow || saveFlowKey !== key) {
    saveFlowKey = key;
    saveFlow = createEquipmentTemplateSaveFlow({
      read: () => { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; } },
      write: (value: unknown) => { localStorage.setItem(key, JSON.stringify(value)); pendingSave.value = value; },
      clear: () => { localStorage.removeItem(key); pendingSave.value = null; },
      save: (intent: any) => saveEquipmentTemplate(
        workshop, intent.payload.fields, intent.request_key, intent.payload.source_entity_id || undefined,
        { templateId: intent.payload.template_id || undefined, expectedUpdatedAt: intent.payload.expected_updated_at || undefined },
        intent,
      ),
    });
  }
  pendingSave.value = saveFlow.pending();
  return saveFlow!;
}

function lifecycleFlow(context: any) {
  const key = `equipment-template-lifecycle:${context.group.id}:${context.user.id}:${context.identity}`;
  const flow = createEquipmentTemplateLifecycleFlow({
    read: () => { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; } },
    write: (value: unknown) => { localStorage.setItem(key, JSON.stringify(value)); pendingLifecycle.value = value; },
    clear: () => { localStorage.removeItem(key); pendingLifecycle.value = null; },
    request: (action: string, templateId: string, requestKey: string) => workshop.request(
      `equipment/templates/${action === "archive" ? "archive" : "restore"}`,
      { template_id: templateId, request_key: requestKey }, context.identity,
    ),
  });
  pendingLifecycle.value = flow.pending();
  return flow;
}

function acceptSavedTemplate(saved: EquipmentTemplate) {
  templates.value = [...templates.value.filter(item => item.id !== saved.id), saved];
  if (saved.archived) {
    if (props.modelValue === saved.id) emit("update:modelValue", null);
    message.value = `“${saved.name}” was saved, but a collection member archived it before confirmation. Restore it before using it for a new item.`;
    return;
  }
  emit("update:modelValue", saved.id);
  emit("apply", saved);
  message.value = `Saved “${saved.name}” for this collection.`;
}

async function changeTemplateLifecycle(action: "archive" | "restore", templateId: string) {
  saving.value = true; error.value = ""; message.value = "";
  try {
    const context = await workshop.refresh();
    const flow = lifecycleFlow(context);
    await flow.change(action, templateId);
    if (action === "archive" && props.modelValue === templateId) emit("update:modelValue", null);
    message.value = action === "archive" ? "Template archived. Its equipment ID and assignment history are retained." : "Template restored to new-item selection.";
    await refresh();
  } catch (cause) { error.value = (cause as Error).message || "The template status could not be confirmed. Retry the saved request."; }
  finally { saving.value = false; }
}

async function retryTemplateLifecycle() {
  if (saving.value || !pendingLifecycle.value) return;
  saving.value = true; error.value = "";
  try {
    const context = await workshop.refresh();
    const flow = lifecycleFlow(context);
    const pending = flow.pending();
    if (!pending) return;
    await flow.resume();
    if (pending.action === "archive" && props.modelValue === pending.template_id) emit("update:modelValue", null);
    message.value = pending.action === "archive" ? "Template archived. Its equipment ID and assignment history are retained." : "Template restored to new-item selection.";
    await refresh();
  } catch (cause) { error.value = (cause as Error).message || "The saved template status request is still awaiting confirmation."; }
  finally { saving.value = false; }
}

async function loadPhotoSources() {
  const matches: PhotoSource[] = [];
  let page = 1;
  let received = 0;
  let total = 0;
  do {
    const response = await api.items.getAll({ page, pageSize: 100, includeArchived: false });
    if (response.error || !response.data) throw response.error || new Error("Photo source items could not be loaded.");
    total = response.data.total;
    received += response.data.items.length;
    matches.push(...response.data.items.filter((item: PhotoSource) => item.entityType?.id === props.entityTypeId));
    if (!response.data.items.length) break;
    page++;
  } while (received < total && page < 1000);
  return matches;
}

function selectTemplate(event: Event) {
  const id = (event.target as HTMLSelectElement).value || null;
  emit("update:modelValue", id);
  const selected = available.value.find(item => item.id === id);
  if (selected) emit("apply", selected);
}

async function saveCurrent() {
  if (!props.entityTypeId || saving.value) return;
  saving.value = true;
  error.value = "";
  message.value = "";
  try {
    const context = await workshop.refresh();
    const flow = await bindSaveFlow(context);
    const fields: Record<string, unknown> = { ...props.fields, entityTypeId: props.entityTypeId };
    if (editing.value && selectedTemplate.value) {
      fields.photo_attachment_id = selectedTemplate.value.photo_attachment_id;
      fields.photo_entity_id = selectedTemplate.value.photo_entity_id;
    }
    const saved = await flow.save({
      fields, sourceEntityId: photoSourceId.value || undefined,
      templateId: editing.value && selectedTemplate.value ? selectedTemplate.value.id : undefined,
      expectedUpdatedAt: editing.value && selectedTemplate.value ? selectedTemplate.value.updated_at : undefined,
      scope: { group_id: context.group.id, user_id: context.user.id, identity: context.identity },
    }) as EquipmentTemplate;
    acceptSavedTemplate(saved);
    editing.value = false;
    photoSourceId.value = "";
  } catch (cause) {
    error.value = (cause as Error).message || "The equipment template could not be saved.";
  } finally { saving.value = false; }
}

async function retryPendingSave() {
  if (saving.value || !pendingSave.value) return;
  saving.value = true;
  error.value = "";
  try {
    const context = await workshop.refresh();
    const flow = await bindSaveFlow(context);
    const saved = await flow.resume() as EquipmentTemplate;
    acceptSavedTemplate(saved);
    editing.value = false;
  } catch (cause) { error.value = (cause as Error).message || "The saved template request could not be confirmed."; }
  finally { saving.value = false; }
}

async function discardRejectedSave() {
  if (saving.value || !pendingSave.value?.rejected) return;
  try {
    const context = await workshop.refresh();
    const flow = await bindSaveFlow(context);
    flow.discardRejected();
    message.value = "The rejected request was discarded after review. Correct the fields and save again.";
    error.value = "";
  } catch (cause) { error.value = (cause as Error).message || "The rejected request could not be discarded."; }
}

async function refreshStaleTemplate() {
  if (saving.value || !pendingSave.value?.stale_version_conflict) return;
  saving.value = true;
  error.value = "";
  staleReviewConfirmed.value = false;
  try {
    const latestTemplates = await listEquipmentTemplates(workshop) as EquipmentTemplate[];
    const templateId = pendingSave.value.payload.template_id;
    const latest = latestTemplates.find(item => item.id === templateId);
    if (!latest) throw new Error("The edited template no longer exists in this collection.");
    templates.value = latestTemplates;
    latestConflictTemplate.value = latest;
    emit("update:modelValue", latest.id);
    emit("apply", latest);
    message.value = `Loaded the latest saved version (${latest.updated_at || "timestamp unavailable"}). Review its fields below before discarding the stale save.`;
  } catch (cause) { error.value = (cause as Error).message || "The latest template could not be loaded."; }
  finally { saving.value = false; }
}

async function discardStaleConflict() {
  if (saving.value || !latestConflictTemplate.value || !staleReviewConfirmed.value) return;
  try {
    const context = await workshop.refresh();
    const flow = await bindSaveFlow(context);
    flow.discardStaleConflict(true);
    latestConflictTemplate.value = null;
    staleReviewConfirmed.value = false;
    editing.value = true;
    message.value = "The stale save was discarded after review. The latest version is loaded; edit the fields and submit a new update when ready.";
  } catch (cause) { error.value = (cause as Error).message || "The stale save could not be discarded."; }
}

watch([selectedCollectionId, () => auth.user?.id], () => {
  saveFlow = null;
  saveFlowKey = "";
  pendingSave.value = null;
  latestConflictTemplate.value = null;
  staleReviewConfirmed.value = false;
  photoSourceId.value = "";
  pendingLifecycle.value = null;
  void refresh();
});

watch(() => props.entityTypeId, () => { emit("update:modelValue", null); editing.value = false; void refresh(); });
onMounted(() => { void refresh(); });
</script>

<template>
  <section class="rounded-md border p-3" aria-label="Collection equipment templates">
    <label class="mb-2 block text-sm font-medium" for="equipment-template-select">Reusable equipment template</label>
    <div class="flex flex-col gap-2 sm:flex-row">
      <select id="equipment-template-select" class="min-w-0 flex-1 rounded-md border bg-background px-3 py-2" :value="modelValue || ''" :disabled="loading" @change="selectTemplate">
        <option value="">No saved template</option>
        <option v-for="item in available" :key="item.id" :value="item.id">{{ item.name }} · {{ item.model_code }}</option>
      </select>
      <Button type="button" variant="outline" :disabled="saving || !entityTypeId" @click="saveCurrent">
        {{ saving ? "Saving…" : editing ? "Update selected template" : "Save shared fields as template" }}
      </Button>
    </div>
    <div v-if="pendingSave" class="mt-2 rounded border border-amber-500 p-2 text-sm" role="status">
      <template v-if="pendingSave.stale_version_conflict">
        The server reports that this template changed after it was read. The old update will not be retried automatically.
        <Button type="button" size="sm" variant="outline" :disabled="saving" class="ml-2" @click="refreshStaleTemplate">{{ saving ? "Refreshing…" : "Refresh latest template" }}</Button>
        <div v-if="latestConflictTemplate" class="mt-2 rounded border p-2">
          <p class="font-medium">Latest saved version · {{ latestConflictTemplate.updated_at || "timestamp unavailable" }}</p>
          <p>{{ latestConflictTemplate.name }} · {{ latestConflictTemplate.manufacturer }} · {{ latestConflictTemplate.model_number }} · {{ latestConflictTemplate.model_code }}</p>
          <p>{{ latestConflictTemplate.description }}</p>
          <p>Tags: {{ latestConflictTemplate.tag_ids.join(", ") || "None" }}</p>
          <label class="mt-2 flex items-start gap-2"><input v-model="staleReviewConfirmed" type="checkbox" /> I reviewed this latest version and confirm the earlier update was rejected as stale.</label>
          <Button type="button" size="sm" variant="outline" :disabled="saving || !staleReviewConfirmed" class="mt-2" @click="discardStaleConflict">Discard stale save after review</Button>
        </div>
      </template>
      <template v-else-if="pendingSave.rejected">
        The server rejected this request ({{ pendingSave.rejection?.status }}): {{ pendingSave.rejection?.message }} Review the fields, then discard this rejected request before submitting a corrected save.
        <Button type="button" size="sm" variant="outline" :disabled="saving" class="ml-2" @click="discardRejectedSave">Discard rejected request after review</Button>
      </template>
      <template v-else>
        A template save is awaiting confirmation. Retry the saved request to confirm its original result.
        <Button type="button" size="sm" variant="outline" :disabled="saving" class="ml-2" @click="retryPendingSave">{{ saving ? "Confirming…" : "Retry pending template save" }}</Button>
      </template>
    </div>
    <div class="mt-2 flex flex-wrap items-center gap-2">
      <Button type="button" variant="outline" size="sm" :disabled="saving" @click="showArchived = !showArchived">{{ showArchived ? "Hide archived templates" : `View archived templates (${archivedTemplates.length})` }}</Button>
      <Button v-if="selectedTemplate" type="button" variant="outline" size="sm" :disabled="saving" @click="changeTemplateLifecycle('archive', selectedTemplate.id)">Archive selected template</Button>
    </div>
    <section v-if="showArchived" class="mt-2 space-y-2 rounded border p-2" aria-label="Archived equipment templates">
      <p v-if="!archivedTemplates.length" class="text-sm text-muted-foreground">No archived templates for this equipment type.</p>
      <article v-for="item in archivedTemplates" :key="item.id" class="flex flex-wrap items-center justify-between gap-2 border-b py-2 last:border-0">
        <div><strong>{{ item.name }}</strong><span class="ml-2 text-sm text-muted-foreground">{{ item.manufacturer }} · {{ item.model_number }} · {{ item.model_code }}</span></div>
        <Button type="button" variant="outline" size="sm" :disabled="saving" @click="changeTemplateLifecycle('restore', item.id)">Restore {{ item.name }}</Button>
      </article>
    </section>
    <div v-if="pendingLifecycle" class="mt-2 rounded border border-amber-500 p-2 text-sm" role="status">
      Template {{ pendingLifecycle.action }} is awaiting confirmation.
      <Button type="button" size="sm" variant="outline" class="ml-2" :disabled="saving" @click="retryTemplateLifecycle">{{ saving ? "Confirming…" : `Retry ${pendingLifecycle.action}` }}</Button>
    </div>
    <div v-if="selectedTemplate" class="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
      <img v-if="!hasItemPhoto && templatePhotoUrl(selectedTemplate)" :src="templatePhotoUrl(selectedTemplate)" class="size-10 rounded object-cover" alt="Template photo fallback" />
      <span>{{ hasItemPhoto ? "This item’s photo takes precedence." : "Template photo is a thumbnail fallback only." }}</span>
      <Button type="button" variant="ghost" size="sm" :disabled="saving" @click="editing = !editing">{{ editing ? "Cancel edit" : "Edit selected template" }}</Button>
    </div>
    <label v-if="entityTypeId" class="mt-2 block text-xs text-muted-foreground">
      Optional template photo source
      <select v-model="photoSourceId" class="mt-1 block w-full rounded border bg-background px-2 py-1">
        <option value="">No source photo</option>
        <option v-for="item in photoSources" :key="item.id" :value="item.id">{{ item.name }} · {{ item.displayId || item.id }}</option>
      </select>
      <span>The server rechecks the item and stores its own photo attachment owner. This photo is only a thumbnail fallback.</span>
    </label>
    <EquipmentTemplateApply v-if="selectedTemplate" :template-id="selectedTemplate.id" :entity-type-id="entityTypeId" :fields="{ ...fields, tagIds: fields.tags, name: selectedTemplate.name }" />
    <p class="mt-2 text-xs text-muted-foreground">Templates copy name, manufacturer, model, description, tags, and model code. Location and per-unit details stay with each item.</p>
    <p v-if="message" class="mt-2 text-sm" role="status">{{ message }}</p>
    <p v-if="error" class="mt-2 text-sm text-destructive" role="alert">{{ error }}</p>
  </section>
</template>
