<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import LabelDesigner from "./LabelDesigner.vue";

// Layout and generate/preview flow adapted from HomeSortStuff's label generator
// (AGPL-3.0, commit 85b96e5060a48dd11db24addfbc63407eed4e74c).
type Item = { id: string; name: string; assetId?: string };
type Template = { id: string; name: string; profile: string; revision: number };
type Review = { entity_id: string; review_id: string; image: string; profile: string; label_mm?: number[] };
type Workspace = {
  items: Item[];
  templates: Template[];
  selectedIds: string[];
  templateId: string;
  marginMm: number;
  gapMm: number;
  reviews: Review[];
  printedReviewIds: string[];
  pages: { image: string; sha256: string }[];
  pendingActions: number;
  busy: boolean;
  actions: {
    select: (ids: string[]) => void;
    template: (id: string) => void;
    layout: (margin: number, gap: number) => void;
    review: () => void;
    printItem: (entityId: string, reviewId: string) => void;
    compose: () => void;
    printPages: () => void;
    downloadPdf: () => void;
    designer: (handle: { canLeave: () => boolean; dispose: () => void } | null) => void;
    designerDirty: (value: boolean) => void;
    designerBusy: (value: boolean) => void;
    recovery: () => void;
  };
};
const props = defineProps<{ workspace: Workspace | null; status: string }>();
const search = ref("");
const designerOpen = ref(false);
const designerRef = ref<InstanceType<typeof LabelDesigner> | null>(null);
watch(() => props.workspace, value => { if (!value) designerOpen.value = false; });
const items = computed(() => (props.workspace?.items || []).filter(item =>
  `${item.name} ${item.assetId || ""}`.toLowerCase().includes(search.value.toLowerCase()),
).slice(0, 100));
const selected = (id: string) => props.workspace?.selectedIds.includes(id) || false;
const canReview = computed(() => !!props.workspace && props.workspace.selectedIds.length > 0 && !!props.workspace.templateId && !props.workspace.busy);
const canCompose = computed(() => {
  const rows = props.workspace?.reviews || [];
  return rows.length > 0 && rows.every(row => row.profile === "letter" && row.label_mm?.join("|") === rows[0]?.label_mm?.join("|"));
});
const templateName = (template: Template) => template.id.startsWith("starter:")
  ? `${template.name} · Starter`
  : `${template.name} · ${template.profile} · r${template.revision}`;
function toggleItem(id: string, checked: boolean) {
  const ids = [...(props.workspace?.selectedIds || [])];
  const index = ids.indexOf(id);
  if (checked && index < 0) ids.push(id);
  if (!checked && index >= 0) ids.splice(index, 1);
  props.workspace?.actions.select(ids);
}
function updateLayout(key: "margin" | "gap", value: string | number) {
  const workspace = props.workspace;
  if (!workspace) return;
  const margin = key === "margin" ? Number(value) : workspace.marginMm;
  const gap = key === "gap" ? Number(value) : workspace.gapMm;
  if (Number.isFinite(margin) && Number.isFinite(gap)) workspace.actions.layout(margin, gap);
}
function toggleDesigner(event: Event) {
  event.preventDefault();
  if (designerOpen.value && designerRef.value && !designerRef.value.canLeave()) return;
  designerOpen.value = !designerOpen.value;
  if (!designerOpen.value) props.workspace?.actions.designer(null);
}
function designerReady(handle: { canLeave: () => boolean; dispose: () => void }) {
  props.workspace?.actions.designer(handle);
}
function designerClosed() {
  props.workspace?.actions.designer(null);
}
</script>

<template>
  <div class="label-generator mx-auto w-full max-w-none space-y-4">
    <header>
      <h1 class="text-2xl font-semibold tracking-tight">Label maker</h1>
      <p class="text-sm text-muted-foreground">Choose current equipment and a saved design, then generate reviewed labels or a Letter sheet.</p>
    </header>

    <template v-if="workspace">
      <div v-if="workspace.pendingActions" class="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 text-sm" role="status">
        {{ workspace.pendingActions }} action{{ workspace.pendingActions === 1 ? ' has' : 's have' }} an unconfirmed result. Check saved actions before retrying.
        <Button variant="outline" class="ml-2" @click="workspace.actions.recovery()">Check saved actions</Button>
      </div>
      <div class="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(20rem,.9fr)]">
        <section class="rounded-lg border bg-card p-4 text-card-foreground">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div><h2 class="text-lg font-semibold">Equipment</h2><p class="text-sm text-muted-foreground">{{ workspace.selectedIds.length }} selected in this collection</p></div>
            <Button variant="outline" :disabled="workspace.selectedIds.length === 0" @click="workspace.actions.select([])">Clear selection</Button>
          </div>
          <Label for="label-equipment-search">Search equipment</Label>
          <Input id="label-equipment-search" v-model="search" type="search" placeholder="Search name or asset code" />
          <div class="mt-3 max-h-64 overflow-auto rounded-md border">
            <label v-for="item in items" :key="item.id" class="flex cursor-pointer items-center gap-3 border-b px-3 py-2 last:border-0 hover:bg-muted/50">
              <input class="h-4 w-4 accent-primary" type="checkbox" :checked="selected(item.id)" @change="toggleItem(item.id, ($event.target as HTMLInputElement).checked)" />
              <span class="min-w-0"><span class="block truncate font-medium">{{ item.name }}</span><span class="text-xs text-muted-foreground">{{ item.assetId || 'No asset code' }}</span></span>
            </label>
            <p v-if="!items.length" class="p-3 text-sm text-muted-foreground">No current equipment matches.</p>
          </div>
        </section>

        <section class="rounded-lg border bg-card p-4 text-card-foreground">
          <h2 class="text-lg font-semibold">Generate labels</h2>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <div class="space-y-2 sm:col-span-2">
              <Label>Saved label design</Label>
              <Select :model-value="workspace.templateId" @update:model-value="workspace.actions.template(String($event || ''))">
                <SelectTrigger aria-label="Saved label template"><SelectValue placeholder="Choose a saved design" /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="template in workspace.templates" :key="template.id" :value="template.id">{{ templateName(template) }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="space-y-2">
              <Label>Page margin (mm)</Label>
              <Input aria-label="Page margin (mm)" type="number" min="0" step="0.1" :model-value="workspace.marginMm" @update:model-value="updateLayout('margin', $event)" />
            </div>
            <div class="space-y-2">
              <Label>Label gap (mm)</Label>
              <Input aria-label="Label gap (mm)" type="number" min="0" step="0.1" :model-value="workspace.gapMm" @update:model-value="updateLayout('gap', $event)" />
            </div>
          </div>
          <p class="mt-3 text-sm text-muted-foreground">Letter sheets follow the selected design’s physical label size. Print at Actual Size / 100%.</p>
          <Button class="mt-4 w-full" :disabled="!canReview" @click="workspace.actions.review()">Review selected labels</Button>
        </section>
      </div>

      <section class="rounded-lg border bg-card p-4 text-card-foreground">
        <h2 class="text-lg font-semibold">Reviewed labels</h2>
        <p v-if="!workspace.reviews.length" class="text-sm text-muted-foreground">Review selected labels to see current item values before output.</p>
        <div v-else class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <article v-for="row in workspace.reviews" :key="row.review_id" class="rounded-md border p-3">
            <img :src="row.image" :alt="'Reviewed label for ' + (workspace.items.find(item => item.id === row.entity_id)?.name || 'equipment')" class="mx-auto max-h-56 max-w-full bg-white object-contain" />
            <p class="truncate text-sm font-medium">{{ workspace.items.find(item => item.id === row.entity_id)?.name || row.entity_id }}</p>
            <Button variant="outline" class="mt-2 w-full" :disabled="workspace.busy || workspace.printedReviewIds.includes(row.review_id)" @click="workspace.actions.printItem(row.entity_id, row.review_id)">{{ workspace.printedReviewIds.includes(row.review_id) ? 'Print submitted' : 'Confirm Pi label print' }}</Button>
          </article>
        </div>
      </section>

      <section class="rounded-lg border bg-card p-4 text-card-foreground">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div><h2 class="text-lg font-semibold">Letter sheet</h2><p class="text-sm text-muted-foreground">Only reviewed Letter labels can be composed.</p></div>
          <div class="flex flex-wrap gap-2">
            <Button variant="outline" :disabled="!canCompose || workspace.busy" @click="workspace.actions.compose()">Compose reviewed Letter sheet</Button>
            <Button variant="outline" :disabled="!workspace.pages.length || workspace.busy" @click="workspace.actions.printPages()">Print reviewed pages</Button>
            <Button :disabled="!workspace.pages.length || workspace.busy" @click="workspace.actions.downloadPdf()">Download reviewed PDF</Button>
          </div>
        </div>
        <div v-if="workspace.pages.length" class="mt-4 grid gap-4 lg:grid-cols-2">
          <img v-for="page in workspace.pages" :key="page.sha256" :src="page.image" :alt="'Reviewed Letter sheet ' + page.sha256" class="h-auto w-full border bg-white" />
        </div>
      </section>

      <section class="rounded-lg border bg-card p-4 text-card-foreground">
        <Button variant="outline" :aria-expanded="designerOpen" @click="toggleDesigner">{{ designerOpen ? 'Close advanced reusable design' : 'Advanced reusable design' }}</Button>
        <template v-if="designerOpen">
        <p class="my-3 text-sm text-muted-foreground">Edit and save reusable layouts for this collection. Draft previews stay separate from reviewed output.</p>
        <LabelDesigner v-if="designerOpen" ref="designerRef" :selected-item="workspace.selectedIds[0]" @ready="designerReady" @closed="designerClosed" @dirty="workspace.actions.designerDirty" @busy="workspace.actions.designerBusy" />
        </template>
      </section>
    </template>
    <p v-else class="rounded-md border p-4 text-sm text-muted-foreground" :role="status.startsWith('Loading') ? 'status' : 'alert'">{{ status }}</p>
  </div>
</template>
