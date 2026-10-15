<script setup lang="ts">
  import BaseCard from "@/components/Base/Card.vue";
  import { Button } from "@/components/ui/button";
  import { Badge } from "@/components/ui/badge";
  import { Label } from "@/components/ui/label";
  import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
  import { Textarea } from "@/components/ui/textarea";
  import { Checkbox } from "@/components/ui/checkbox";
  import { toast } from "@/components/ui/sonner";
  import ActionDialog from "./ActionDialog.vue";
  import LocationSelector from "@/components/Location/Selector.vue";
  import type { EntitySummary } from "@/lib/api/types/data-contracts";
  const props = defineProps<{ itemId: string; compact?: boolean }>();
  const workshop = useWorkshop();
  const { manager, busy } = workshop;
  const { selectedId } = useCollections();
  const data = ref<any>(null), loan = ref<any>(null), history = ref<any[]>([]), kit = ref<any>(null);
  const loading = ref(true), error = ref(""), mode = ref<"condition" | "return" | null>(null);
  const dialogKind = ref<"condition" | "return">("condition");
  const state = ref(""), notes = ref<Record<string, string>>({}), verified = ref<Record<string, boolean>>({});
  const destinations = ref<Record<string, EntitySummary | null>>({});
  let generation = 0;
  const returnItems = computed<any[]>(() => kit.value?.kit ? kit.value.entities : data.value ? [data.value.entity] : []);
  const returnNotes = computed(() => history.value.flatMap(row => row.return_notes || []));
  function date(value: string) { return new Date(value.includes("T") ? value : value.replace(" ", "T") + "Z").toLocaleString(); }
  async function load() {
    const revision = ++generation;
    loading.value = true; error.value = ""; mode.value = null; data.value = null; loan.value = null; history.value = [];
    try {
      await workshop.refresh();
      const [entity, loans, rows] = await Promise.all([workshop.request("entity?id=" + props.itemId), workshop.request<any[]>("loans"), props.compact ? Promise.resolve([]) : workshop.request<any[]>("history?entity=" + props.itemId)]);
      if (revision !== generation) return;
      data.value = entity; loan.value = loans.find(row => row.entity_id === props.itemId); history.value = rows;
    } catch (cause) { if (revision === generation) error.value = (cause as Error).message; }
    finally { if (revision === generation) loading.value = false; }
  }
  async function reviewReturn() {
    error.value = "";
    try { kit.value = await workshop.request("kit?id=" + props.itemId); notes.value = {}; verified.value = {}; destinations.value = Object.fromEntries(returnItems.value.map(item => [item.id, item.parent || null])); dialogKind.value = "return"; mode.value = "return"; }
    catch (cause) { error.value = (cause as Error).message; }
  }
  async function confirm() {
    error.value = "";
    try {
      if (mode.value === "condition") {
        await workshop.write("condition", { entity_id: props.itemId, state: state.value }, "Review condition", props.itemId);
        toast.success("Condition saved in C-Crate.");
      } else if (mode.value === "return") {
        if (kit.value?.kit && returnItems.value.some(item => !verified.value[item.id])) throw new Error("Physically verify every kit component before confirming.");
        await workshop.write("return", { targets: returnItems.value.map(item => ({ entity_id: item.id, condition: null, destination_id: destinations.value[item.id]?.id || null, clear_destination: !destinations.value[item.id], note: null, return_note: (notes.value[item.id] || "").trim() })), verified: Object.keys(verified.value).filter(id => verified.value[id]), kit_versions: kit.value?.versions || {} }, "Administrative return", props.itemId);
        toast.success("Return recorded with your name and completion time.");
      }
      mode.value = null; await load();
    } catch (cause) { error.value = (cause as Error).message; }
  }
  watch([() => props.itemId, selectedId], load, { immediate: true });
  onBeforeUnmount(() => { generation++; notes.value = {}; });
  onBeforeRouteLeave(() => { if (busy.value) return false; if (mode.value === "return" && Object.values(notes.value).some(Boolean)) return window.confirm("Discard these unsaved return notes?"); });
</script>
<template>
  <BaseCard>
    <template #title>Borrowing</template>
    <div class="space-y-4 p-4 sm:px-6">
      <p v-if="loading" class="text-sm text-muted-foreground">Loading borrowing information…</p>
      <template v-else-if="data">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="space-y-2"><Badge variant="outline">{{ data.condition }}</Badge><p>{{ loan ? "Currently with " + loan.borrower : "No current borrower." }}</p><p v-if="data.blocker" class="text-sm text-muted-foreground">Checkout blocked: {{ data.blocker }}</p></div>
          <Button v-if="compact" as-child variant="outline"><NuxtLink :to="'/item/' + itemId + '/loans'">Loans &amp; return notes</NuxtLink></Button>
          <div v-else-if="manager" class="flex flex-wrap gap-2"><Button variant="outline" :disabled="busy" @click="state = data.condition; dialogKind = 'condition'; mode = 'condition'">Review condition</Button><Button v-if="loan" :disabled="busy" @click="reviewReturn">Record return</Button></div>
        </div>
        <template v-if="!compact">
          <div class="space-y-3 border-t pt-4"><h3 class="font-medium">Return notes</h3><p v-if="!returnNotes.length" class="text-sm text-muted-foreground">No return notes recorded for this item.</p><article v-for="(note, index) in returnNotes" :key="index" class="space-y-1 border-l-2 pl-4"><p class="whitespace-pre-wrap">{{ note.text }}</p><p class="text-sm text-muted-foreground">{{ note.author }} · {{ date(note.created_at) }}</p></article></div>
          <div class="space-y-3 border-t pt-4"><h3 class="font-medium">Borrowing history</h3><p v-if="!history.length" class="text-sm text-muted-foreground">No borrowing activity yet.</p><p v-for="row in history" :key="row.id" class="text-sm"><span class="capitalize">{{ row.action }}</span> · {{ row.status }} · {{ row.actor }} · {{ date(row.created_at) }}</p></div>
        </template>
      </template>
      <p v-if="error && !mode" role="alert" class="text-sm text-destructive">{{ error }} <Button variant="link" @click="load">Reload</Button></p>
    </div>
    <ActionDialog :model-value="mode !== null" :title="dialogKind === 'return' ? 'Review administrative return' : 'Review condition'" :description="data?.entity.name" :busy="busy" @update:model-value="!$event && (mode = null)">
      <template v-if="mode === 'condition'"><Label>Condition</Label><Select v-model="state"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem v-for="value in data.states" :key="value" :value="value">{{ value }}</SelectItem></SelectContent></Select><p class="text-sm text-muted-foreground">Mark Ready only after physically checking the item.</p></template>
      <template v-else-if="mode === 'return'"><p class="text-sm text-muted-foreground">Borrower: {{ loan?.borrower }}. This return is recorded under {{ workshop.context.value?.user.name }}. Choose an optional return parent. Condition stays as recorded.</p><div v-for="item in returnItems" :key="item.id" class="space-y-2"><LocationSelector v-model="destinations[item.id]" :current-location="item" />
<Label :for="'return-note-' + item.id">Return note: {{ item.name }}</Label><Textarea :id="'return-note-' + item.id" v-model="notes[item.id]" :maxlength="1000" /><label v-if="kit?.kit" class="flex items-center gap-2"><Checkbox v-model="verified[item.id]" />Physically verified: {{ item.name }}</label></div></template>
      <p v-if="error" role="alert" class="text-sm text-destructive">{{ error }} <NuxtLink to="/workshop/recovery" class="underline">Open recovery</NuxtLink></p>
      <template #actions><template v-if="mode !== null"><Button variant="outline" :disabled="busy" @click="mode = null">Cancel</Button><Button :disabled="busy" @click="confirm">{{ mode === 'condition' ? "Confirm condition" : "Confirm return" }}</Button></template></template>
    </ActionDialog>
  </BaseCard>
</template>
