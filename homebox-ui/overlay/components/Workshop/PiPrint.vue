<script setup lang="ts">
import DeviceReconnect from "./DeviceReconnect.vue";
import { Button } from "@/components/ui/button";
import { Printer } from "lucide-vue-next";
import { toast } from "@/components/ui/sonner";
const props = defineProps<{ entityId?: string; id?: string }>();
const workshop = useWorkshop();
const { manager, busy } = workshop;
const templates = ref<any[]>([]), templateId = ref(""), preview = ref<any>(null), error = ref(""), loaded = ref(false), sending = ref(false), uncertain = ref(false);
let disposed = false, generation = 0;
const isItem = computed(() => !!props.entityId);
const itemId = computed(() => props.entityId || props.id || "");
const selected = computed(() => templates.value.find(row => row.id === templateId.value));
async function loadTemplates() {
  let current = generation;
  try { await workshop.refresh(); if (disposed) return; current = ++generation; const identity = workshop.context.value?.identity, group = workshop.context.value?.group.id; const rows = await workshop.request<any[]>("labels/templates"); if (disposed || current !== generation || identity !== workshop.context.value?.identity || group !== workshop.context.value?.group.id) return; templates.value = rows; if (!templates.value.some(row => row.id === templateId.value)) templateId.value = templates.value[0]?.id || ""; loaded.value = true; }
  catch (cause) { if (!disposed && current === generation) error.value = (cause as Error).message; }
}
onMounted(loadTemplates);
onBeforeUnmount(() => { disposed = true; generation++; });
function contextChanged(next: unknown[], previous: unknown[]) { preview.value = null; sending.value = false; uncertain.value = false; const changed = next[2] !== previous[2] || next[3] !== previous[3]; if (changed) { generation++; templates.value = []; templateId.value = ""; loaded.value = false; if (previous[2] != null || previous[3] != null) void loadTemplates(); } else generation++; }
watch(() => [props.entityId, props.id, workshop.context.value?.identity, workshop.context.value?.group.id], contextChanged);
async function review() {
  error.value = ""; preview.value = null; const current = ++generation, identity = workshop.context.value?.identity, selectedId = templateId.value, selectedRevision = selected.value?.revision, entityId = itemId.value;
  try {
    if (isItem.value) {
      if (!selected.value) throw Error("Choose a saved template first.");
      const result = await workshop.request("labels/preview", { mode: "item", entity_id: itemId.value, template_id: selected.value.id, template_revision: selected.value.revision });
      if (disposed || current !== generation || !isItem.value || entityId !== itemId.value || identity !== workshop.context.value?.identity || selectedId !== templateId.value || selectedRevision !== selected.value?.revision) return; preview.value = result;
    } else {
      // Legacy native location-label flow remains available for storage QR labels.
      const result = await workshop.request("labels/preview", { entity_id: itemId.value }); if (disposed || current !== generation || entityId !== itemId.value || identity !== workshop.context.value?.identity) return; preview.value = result;
    }
  } catch (cause) { if (!disposed && current === generation) error.value = (cause as Error).message; }
}
async function print() {
  if (sending.value) return;
  error.value = ""; sending.value = true;
  try {
    await workshop.write("labels/print", { entity_id: itemId.value, review_id: preview.value?.review_id }, "Print item label", itemId.value);
    toast("Pi printer confirmed this request. Inspect the physical label."); preview.value = null;
  } catch (cause) { error.value = (cause as Error).message; if (error.value.includes("Load the reviewed 40 x 28 mm SUPVAN stock")) { uncertain.value = false; preview.value = null; } else uncertain.value = true; }
  finally { sending.value = false; }
}
</script>
<template>
  <div v-if="manager" class="space-y-3 rounded-md border p-3">
    <p class="text-sm font-medium">{{ isItem ? "Review item label" : "Storage QR label" }}</p>
    <label v-if="isItem" class="block text-sm">Saved label template
      <select v-model="templateId" class="mt-1 block min-h-10 w-full rounded border px-2" @change="generation++; preview = null; uncertain = false">
        <option value="" disabled>Choose a template</option><option v-for="row in templates" :key="row.id" :value="row.id">{{ row.name }} · {{ row.profile }} · r{{ row.revision }}</option>
      </select>
    </label>
    <img v-if="preview" :src="preview.image" :alt="isItem ? 'Reviewed item label preview' : 'Storage QR label preview'" class="mx-auto max-h-52 max-w-full rounded bg-white p-2" />
    <p v-if="isItem" class="text-sm text-muted-foreground">Preview uses current native item values. Printing requires the separate confirmation below.</p>
    <p v-if="error" role="alert" class="text-sm text-destructive">{{ error }} <NuxtLink v-if="uncertain" to="/workshop/recovery" class="underline">Open recovery</NuxtLink></p>
    <DeviceReconnect device="printer" />
    <div class="flex gap-2"><Button variant="outline" :disabled="busy || !loaded && isItem" @click="review">{{ isItem ? "Review current item" : "Preview storage QR" }}</Button><Button :disabled="busy || sending || uncertain || !preview || !preview.review_id" @click="print"><Printer class="mr-2 size-4" />Confirm one Pi print</Button></div>
  </div>
</template>
