<script setup lang="ts">
  import { computed, ref, watch } from "vue";
  import ActionDialog from "./ActionDialog.vue";
  import LocationSelector from "@/components/Location/Selector.vue";
  import { Button } from "@/components/ui/button";
  import { Label } from "@/components/ui/label";
  import { Textarea } from "@/components/ui/textarea";
  import { toast } from "@/components/ui/sonner";
  import { useItemActions } from "@/composables/use-item-actions";
  import { useWorkshop } from "@/composables/use-workshop";
  import type { EntitySummary } from "@/lib/api/types/data-contracts";

  type KitRow = { id: string; name: string };
  type ItemRecord = { entity?: EntitySummary & { assetId?: string; serialNumber?: string } } | null;

  const actions = useItemActions();
  const workshop = useWorkshop();
  const { state } = actions;
  const records = ref<Record<string, ItemRecord>>({});
  const selectedDestination = ref<EntitySummary | null>(null);
  const badgeCode = ref(""), itemCode = ref(""), returnScanCode = ref(""), working = ref(false);
  const kind = computed(() => state.request?.kind || "checkout");
  const busy = computed(() => ["submitting", "verifying"].includes(state.phase));
  const open = computed(() => state.phase !== "closed");
  const pendingActions = computed(() => { actions.pendingRevision.value; return actions.pending(); });
  const pendingError = computed(() => { actions.pendingRevision.value; return actions.pendingError(); });
  const allCheckoutItemsVerified = computed(() => !!state.verificationId && state.requiredItems.every(id => state.verifiedItems.includes(id)));
  const returnKitItems = computed(() => (state.draft.kit_items as KitRow[] | undefined) || []);
  const verifiedReturnItems = computed(() => (state.draft.verified as string[] | undefined) || []);
  const allReturnItemsVerified = computed(() => returnKitItems.value.every(row => verifiedReturnItems.value.includes(row.id)));
  const title = computed(() => ({ checkout: "Check out equipment", checkin: "Check in equipment", cart: "Add to cart", note: "Add an item note" }[kind.value]));
  const cartNoteItemId = computed(() => state.request?.kind === "cart" ? state.request.itemId : state.itemIds[0] || "");
  const description = computed(() => state.itemIds.map(id => records.value[id]?.entity?.name || id).join(", "));
  let generation = 0;
  watch(() => [state.phase, state.itemIds.join(","), state.draft.destination_id || "", workshop.context.value?.identity || ""], async ([phase, ids, destinationId], _old, onCleanup) => {
    if (!ids || phase === "closed") { records.value = {}; return; }
    const current = ++generation;
    onCleanup(() => { if (generation === current) generation++; });
    const selected = String(ids).split(",");
    const entries = await Promise.all(selected.map(async id => {
      try { return [id, await workshop.request(`entity?id=${encodeURIComponent(id)}`)] as const; }
      catch { return [id, null] as const; }
    }));
    if (current !== generation) return;
    records.value = Object.fromEntries(entries);
    if (!destinationId) { selectedDestination.value = selected[0] ? records.value[selected[0] || ""]?.entity?.parent || null : null; return; }
    const destination = await workshop.request(`entity?id=${encodeURIComponent(String(destinationId))}`).catch(() => null);
    if (current !== generation || String(destinationId) !== String(state.draft.destination_id || "")) return;
    selectedDestination.value = destination?.entity || (destination?.id ? destination : null);
  });
  watch(() => [state.phase, state.itemIds.join(","), workshop.context.value?.identity || ""], ([phase, ids], oldValue) => {
    if (phase === "closed" || oldValue?.[1] !== ids || oldValue?.[2] !== workshop.context.value?.identity) {
      badgeCode.value = ""; itemCode.value = ""; returnScanCode.value = "";
      selectedDestination.value = null;
    }
  });
  watch(() => actions.changed.value, value => {
    if (!value) return;
    toast.success("Action confirmed.");
  });
  function updateReturnLocation(value: EntitySummary | null) { selectedDestination.value = value; actions.setDraft({ destination_id: value?.id || "" }); }
  async function scanBadge() {
    working.value = true;
    try { await actions.verifyBadge(badgeCode.value); badgeCode.value = ""; }
    catch { /* Controller keeps the message and draft visible. */ }
    finally { working.value = false; }
  }
  async function scanItem() {
    working.value = true;
    try { await actions.verifyItem(itemCode.value); itemCode.value = ""; }
    catch { /* Controller keeps the message and scan field. */ }
    finally { working.value = false; }
  }
  async function scanReturnItem() {
    working.value = true;
    try { await actions.verifyReturnItem(returnScanCode.value); returnScanCode.value = ""; }
    catch { /* Keep scan evidence and error visible for review. */ }
    finally { working.value = false; }
  }
  async function confirm() {
    working.value = true;
    try { await actions.confirm(); }
    catch { /* Controller classifies the result and retains the draft. */ }
    finally { working.value = false; }
  }
  async function reconcile() {
    working.value = true;
    try { await actions.reconcile(); }
    catch { /* Recovery remains available. */ }
    finally { working.value = false; }
  }
  function updateNote(id: string, value: string | number) { actions.setNote(id, String(value)); }
  function removeCheckoutItem(id: string) {
    const next = state.itemIds.filter(value => value !== id);
    void actions.changeSelection(next, (state.request as any)?.cartRevision ?? 0).catch(() => {});
  }
</script>

<template>
  <section v-if="!open && pendingActions.length" aria-label="Unconfirmed item actions" class="mb-3 rounded border border-amber-500 p-3">
    <p class="mb-2 text-sm">An item action has no confirmed result. Check its saved result before continuing.</p>
    <Button v-for="row in pendingActions" :key="row.request_key" variant="outline" class="mr-2 mb-2" data-testid="item-action-resume" @click="actions.recoverPending(row)">
      Review {{ row.kind }} result · {{ row.item_ids.length }} item{{ row.item_ids.length === 1 ? '' : 's' }}
    </Button>
  </section>
  <p v-if="pendingError" role="alert" class="mb-3 rounded border border-destructive p-3 text-sm">{{ pendingError }}</p>
  <ActionDialog :model-value="open" :title="title" :description="description" :busy="busy" @update:model-value="!$event && actions.close()">
    <div v-if="state.phase === 'loading'" role="status" class="py-6 text-sm">Loading the current equipment status…</div>
    <div v-else-if="state.phase === 'success'" data-testid="item-action-receipt" role="status" class="py-4">Action confirmed.</div>
    <div v-else class="space-y-4 py-2">
      <section v-for="id in state.itemIds" :key="id" class="rounded-md border p-3">
        <p class="font-medium">{{ records[id]?.entity?.name || id }}</p>
        <p class="text-sm text-muted-foreground">{{ records[id]?.entity?.assetId || records[id]?.entity?.serialNumber || 'No serial or asset ID' }}</p>
        <p class="text-sm">Status: {{ state.status.find(row => row.id === id)?.availability || 'unknown' }}</p>
        <p v-if="state.status.find(row => row.id === id)?.blocker" class="text-sm text-destructive">{{ state.status.find(row => row.id === id)?.blocker }}</p>
        <p v-if="kind === 'checkout' && state.status.find(row => row.id === id)?.availability !== 'available'" role="alert" class="text-sm text-destructive">This item cannot be checked out until its current status is reviewed.</p>
        <Button v-if="kind === 'checkout' && state.request?.source === 'cart' && state.itemIds.length > 1" variant="outline" class="mt-2" :disabled="busy" :aria-label="`Remove ${records[id]?.entity?.name || id} from this checkout`" @click="removeCheckoutItem(id)">Remove from this checkout</Button>
      </section>

      <template v-if="kind === 'checkout'">
        <p v-if="state.request?.source === 'cart'" class="text-sm text-muted-foreground">The selected cart items and their private notes are checked together. Adding items to the cart does not reserve them.</p>
        <div class="space-y-2">
          <Label for="item-action-badge">Scan matching member badge</Label>
          <div class="flex gap-2"><input id="item-action-badge" v-model="badgeCode" data-testid="item-action-badge" autocomplete="off" class="min-w-0 flex-1 rounded border px-3 py-2" /><Button data-testid="item-action-verify-badge" :disabled="busy || !badgeCode.trim()" @click="scanBadge">Verify badge</Button></div>
        </div>
        <div v-if="state.verificationId" class="space-y-2">
          <p class="text-sm">Verified borrower: {{ workshop.context.value?.user.name }}. Scanned {{ state.verifiedItems.length }} of {{ state.requiredItems.length }} required item or kit codes.</p>
          <Label for="item-action-scan">Scan each selected item and required kit component</Label>
          <div class="flex gap-2"><input id="item-action-scan" v-model="itemCode" data-testid="item-action-scan" autocomplete="off" class="min-w-0 flex-1 rounded border px-3 py-2" @keydown.enter.prevent="scanItem" /><Button data-testid="item-action-verify-item" :disabled="busy || !itemCode.trim()" @click="scanItem">Verify item</Button></div>
        </div>
        <div v-for="id in state.itemIds" :key="`checkout-note-${id}`" class="space-y-2">
          <Label :for="`checkout-note-${id}`">Optional checkout note for {{ records[id]?.entity?.name || id }}</Label>
          <Textarea :id="`checkout-note-${id}`" :model-value="state.draft.notes?.[id] || ''" maxlength="1000" @update:model-value="value => updateNote(id, value)" />
        </div>
      </template>

      <template v-else-if="kind === 'checkin'">
        <p class="text-sm text-muted-foreground">Borrower: {{ state.status[0]?.loan?.borrower_name || state.status[0]?.loan?.borrower_id || 'Current borrower' }}. Returning as {{ workshop.context.value?.user.name }}.</p>
        <LocationSelector v-model="selectedDestination" :current-location="records[state.itemIds[0] || '']?.entity" label="Return destination" @update:model-value="updateReturnLocation" />
        <p v-if="state.draft.destination_id" class="text-xs text-muted-foreground">Defaults to the assigned storage location. Choose a different destination above if needed.</p>
        <div v-for="id in state.itemIds" :key="`return-note-${id}`" class="space-y-2"><Label :for="`return-note-${id}`">Optional return note</Label><Textarea :id="`return-note-${id}`" :model-value="state.draft.return_note || ''" maxlength="1000" @update:model-value="value => actions.setDraft({ return_note: value })" /></div>
        <div v-if="returnKitItems.length" class="space-y-2">
          <p class="text-sm">Scan every component in the current kit ({{ verifiedReturnItems.length }} of {{ returnKitItems.length }} verified).</p>
          <div class="flex gap-2"><input v-model="returnScanCode" data-testid="item-action-return-scan" aria-label="Scan returned kit component" autocomplete="off" class="min-w-0 flex-1 rounded border px-3 py-2" @keydown.enter.prevent="scanReturnItem" /><Button :disabled="busy || !returnScanCode.trim()" data-testid="item-action-return-verify" @click="scanReturnItem">Verify component</Button></div>
          <ul class="text-sm"><li v-for="row in returnKitItems" :key="row.id">{{ verifiedReturnItems.includes(row.id) ? 'Verified' : 'Needs scan' }}: {{ row.name }}</li></ul>
        </div>
        <div class="space-y-2"><Label for="item-action-problem">Report a problem (requires a description)</Label><Textarea id="item-action-problem" :model-value="state.draft.problem || ''" maxlength="1000" @update:model-value="value => actions.setDraft({ problem: value })" /></div>
      </template>

      <template v-else-if="kind === 'note'">
        <Label for="item-action-note">Append a note</Label>
        <Textarea id="item-action-note" data-testid="item-action-note-input" :model-value="state.draft.note || ''" maxlength="1000" @update:model-value="value => actions.setDraft({ note: value })" />
      </template>

      <template v-else>
        <p class="text-sm text-muted-foreground">Adding an item to your cart does not reserve it or guarantee later checkout.</p>
        <Label for="item-action-cart-note">Private note for this item</Label>
        <Textarea id="item-action-cart-note" maxlength="1000" :model-value="state.draft.notes?.[cartNoteItemId] || ''" @update:model-value="value => updateNote(cartNoteItemId, value)" />
      </template>

      <div v-if="state.discardPrompt" role="alertdialog" class="space-y-2 rounded border border-destructive p-3"><p>Discard your unsaved changes?</p><div class="flex gap-2"><Button variant="outline" @click="state.discardPrompt = false">Keep editing</Button><Button variant="destructive" data-testid="item-action-discard" @click="actions.discard()">Discard</Button></div></div>
      <div v-if="state.error" role="alert" class="space-y-2 text-sm text-destructive"><p>{{ state.error }}</p><Button v-if="state.phase === 'uncertain'" variant="outline" data-testid="item-action-reconcile" :disabled="working" @click="reconcile">Check saved result</Button><NuxtLink v-if="state.phase === 'uncertain'" to="/workshop/recovery" class="underline">Open Recovery</NuxtLink></div>
    </div>
    <template #actions>
      <Button v-if="state.phase !== 'closed'" variant="outline" data-testid="item-action-cancel" :disabled="busy" @click="actions.close()">Cancel</Button>
      <Button v-if="state.phase !== 'uncertain' && state.phase !== 'loading'" data-testid="item-action-confirm" :disabled="busy || (kind === 'checkout' && !allCheckoutItemsVerified) || (kind === 'checkin' && !allReturnItemsVerified) || (kind === 'note' && !state.draft.note?.trim())" @click="confirm">{{ kind === 'checkout' ? 'Confirm checkout' : kind === 'checkin' ? 'Confirm check-in' : kind === 'note' ? 'Save note' : 'Add to cart' }}</Button>
    </template>
  </ActionDialog>
</template>
