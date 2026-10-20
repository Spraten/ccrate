<script setup lang="ts">
  import { onMounted, onBeforeUnmount, nextTick, ref, watch } from "vue";
  import { useItemActions } from "@/composables/use-item-actions";
  import type { ItemActionKind, ItemActionStatus } from "@/lib/item-action-contracts";

  const props = defineProps<{ itemId: string; compact?: boolean }>();
  const actions = useItemActions();
  const status = ref<ItemActionStatus | null>(null), loading = ref(true), error = ref("");
  let generation = 0, focusAfterRefresh = false;
  async function load(refresh = false) {
    const current = ++generation;
    // Keep the row trigger mounted while refreshing after a completed action so
    // the dialog can restore keyboard focus to its opener.
    loading.value = !status.value; error.value = "";
    try {
      const row = await actions.loadStatus(props.itemId, refresh);
      if (current === generation) status.value = row || null;
    } catch (cause) { if (current === generation) error.value = (cause as Error).message; }
    finally { if (current === generation) loading.value = false; }
  }
  function open(kind: ItemActionKind, event: MouseEvent) {
    focusAfterRefresh = true;
    void actions.open({ kind, itemId: props.itemId, source: "item-row" }, event.currentTarget as HTMLElement).catch(() => { focusAfterRefresh = false; });
  }
  const changed = actions.changed;
  watch(changed, value => {
    if (value?.kind === "cart" || !value?.itemIds.includes(props.itemId)) return;
    void load(true).then(async () => {
      if (!focusAfterRefresh) return;
      focusAfterRefresh = false;
      await nextTick();
      if (document.activeElement === document.body) (document.querySelector(`[data-item-action-focus-fallback][aria-label="Actions for ${CSS.escape(props.itemId)}"]`) as HTMLElement | null)?.focus();
    });
  });
  watch(() => props.itemId, () => { void load(); });
  onMounted(load);
  onBeforeUnmount(() => { generation++; });
</script>

<template>
  <div class="flex flex-wrap items-center justify-end gap-2" data-item-action-focus-fallback tabindex="-1" :aria-label="`Actions for ${itemId}`">
    <span v-if="loading" class="text-xs text-muted-foreground">Checking actions…</span>
    <span v-else-if="error || !status" role="status" class="text-xs text-muted-foreground">Actions unavailable</span>
    <details v-else-if="compact" class="relative">
      <summary class="cursor-pointer rounded border px-3 py-2 text-sm">Actions</summary>
      <div class="absolute right-0 z-10 mt-1 flex min-w-40 flex-col gap-1 rounded border bg-background p-2 shadow">
        <button v-if="status.availability === 'available'" data-testid="item-action-checkout" class="rounded px-3 py-2 text-left text-sm" @click="open('checkout', $event)">Check out</button>
        <button v-if="status.can_checkin" data-testid="item-action-checkin" class="rounded px-3 py-2 text-left text-sm" @click="open('checkin', $event)">Check in</button>
        <button v-if="status.availability !== 'unknown'" data-testid="item-action-cart" class="rounded px-3 py-2 text-left text-sm" @click="open('cart', $event)">Add to cart</button>
        <button v-if="status.can_add_note" data-testid="item-action-note" class="rounded px-3 py-2 text-left text-sm" @click="open('note', $event)">Add note</button>
        <span v-if="status.availability === 'unknown'" class="px-3 py-2 text-xs text-muted-foreground">Status unknown</span>
      </div>
    </details>
    <template v-else>
      <button v-if="status.availability === 'available'" data-testid="item-action-checkout" class="rounded border px-3 py-2 text-sm" @click="open('checkout', $event)">Check out</button>
      <button v-if="status.can_checkin" data-testid="item-action-checkin" class="rounded border px-3 py-2 text-sm" @click="open('checkin', $event)">Check in</button>
      <button v-if="status.availability !== 'unknown'" data-testid="item-action-cart" class="rounded border px-3 py-2 text-sm" @click="open('cart', $event)">Add to cart</button>
      <button v-if="status.can_add_note" data-testid="item-action-note" class="rounded border px-3 py-2 text-sm" @click="open('note', $event)">Add note</button>
      <span v-if="status.availability === 'unknown'" class="text-xs text-muted-foreground">Status unknown</span>
    </template>
  </div>
</template>
