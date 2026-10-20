<script setup lang="ts">
import { inventoryNoteRequestKey } from '@/lib/child-item-groups.js';
type Unit = Record<string, any> & { id: string; name?: string; displayId?: string; status?: string; storagePath?: string; thumbnail?: { entity_id: string; attachment_id: string } | null };
type Group = { key: string; name: string; items: Unit[]; recordCount: number; nativeQuantity: number; statusCounts: Record<string, number>; thumbnail: Unit['thumbnail']; locationSummary: string };
const props = defineProps<{ groups: Group[]; page: number; pageSize: number; recentNotes?: Record<string, any>; noteLoadingKeys?: string[]; noteLoadedKeys?: string[] }>();
const emit = defineEmits<{ 'update:page': [page: number]; 'load-notes': [request: { key: string; entityIds: string[]; refresh?: boolean }]; 'refresh-items': [] }>();
const api = useUserApi();
const itemActions = useItemActions();
const actionStatuses = reactive(new Map<string, any>());
const expanded = ref(new Set<string>());
const visible = computed(() => props.groups.slice((props.page - 1) * props.pageSize, props.page * props.pageSize));
watch([() => props.groups.length, () => props.pageSize], () => {
  const lastPage = Math.max(1, Math.ceil(props.groups.length / Math.max(1, props.pageSize)));
  if (props.page > lastPage) emit('update:page', lastPage);
});
function toggle(group: Group) { const next = new Set(expanded.value); if (next.has(group.key)) next.delete(group.key); else { next.add(group.key); emit('load-notes', { key: group.key, entityIds: group.items.map(item => item.id) }); } expanded.value = next; }
function noteKey(group: Group) { return inventoryNoteRequestKey(group.key, group.items.map(item => item.id)); }
function unitNoteKey(group: Group, unit: Unit) { return inventoryNoteRequestKey(group.key, [unit.id]); }
function statusLabel(status: string) { return ({ available: 'Available', checked_out: 'Checked out', blocked: 'Blocked', archived: 'Archived', unknown: 'Unknown' } as Record<string, string>)[status] || 'Unknown'; }
function unitStatus(unit: Unit) { return unit.archived ? 'archived' : actionStatuses.get(unit.id)?.availability || unit.status || 'unknown'; }
function groupCounts(group: Group) {
  const counts = { available: 0, checked_out: 0, blocked: 0, archived: 0, unknown: 0 };
  for (const unit of group.items) {
    const raw = unitStatus(unit);
    const key = raw === 'checkedOut' ? 'checked_out' : raw;
    counts[key in counts ? key as keyof typeof counts : 'unknown']++;
  }
  return counts;
}
watch(itemActions.changed, async result => {
  if (!result || result.kind === 'cart') return;
  const loaded = new Set(props.groups.flatMap(group => group.items.map(item => item.id)));
  for (const id of result.itemIds) {
    if (!loaded.has(id)) continue;
    try { actionStatuses.set(id, await itemActions.loadStatus(id, true)); }
    catch { actionStatuses.delete(id); }
    const group = props.groups.find(row => row.items.some(item => item.id === id));
    if (group && expanded.value.has(group.key)) emit('load-notes', { key: group.key, entityIds: [id], refresh: true });
  }
  // The parent reruns its existing Homebox query, preserving search, location,
  // tag, photo and archive filters while reconciling moved rows and full paths.
  emit('refresh-items');
});
function photoUrl(photo: Unit['thumbnail']) { return photo ? api.authURL(`/entities/${encodeURIComponent(photo.entity_id)}/attachments/${encodeURIComponent(photo.attachment_id)}`) : ''; }
</script>

<template>
  <section class="space-y-3" aria-label="Grouped inventory">
    <article v-for="group in visible" :key="group.key" class="overflow-hidden rounded-lg border bg-card">
      <button class="flex w-full items-center gap-3 p-3 text-left" :aria-expanded="expanded.has(group.key)" @click="toggle(group)">
        <img v-if="group.thumbnail" :src="photoUrl(group.thumbnail)" alt="" class="size-14 rounded object-cover" />
        <div v-else class="flex size-14 shrink-0 items-center justify-center rounded bg-muted text-xs text-muted-foreground">No photo</div>
        <div class="min-w-0 flex-1"><strong class="block truncate">{{ group.name }}</strong><span class="block truncate text-sm text-muted-foreground">{{ group.locationSummary }}</span>
          <span class="block text-xs text-muted-foreground">{{ groupCounts(group).available }} available · {{ groupCounts(group).checked_out }} checked out · {{ groupCounts(group).blocked }} blocked · {{ groupCounts(group).archived }} archived · {{ groupCounts(group).unknown }} unknown</span>
        </div>
        <span class="whitespace-nowrap font-semibold">×{{ group.recordCount }} <span aria-hidden="true">{{ expanded.has(group.key) ? '⌄' : '›' }}</span></span>
      </button>
      <div v-if="expanded.has(group.key)" class="divide-y border-t">
        <div v-for="unit in group.items" :key="unit.id" class="flex flex-wrap items-center gap-3 p-3">
          <img v-if="unit.thumbnail" :src="photoUrl(unit.thumbnail)" alt="" class="size-10 rounded object-cover" />
          <div class="min-w-0 flex-1"><strong class="block truncate">{{ unit.name || 'Unnamed item' }}</strong><span class="block text-sm text-muted-foreground">{{ unit.displayId || 'No assigned ID' }} · {{ statusLabel(unitStatus(unit)) }}</span><span class="block truncate text-xs text-muted-foreground">{{ unit.storagePath || 'Location unknown' }} · Serial {{ unit.serialNumber || 'unknown' }} · {{ Number(unit.quantity) || 0 }} native quantity</span><span class="block truncate text-xs text-muted-foreground">Recent note: {{ recentNotes?.[unit.id]?.text || (noteLoadingKeys?.includes(unitNoteKey(group, unit)) || noteLoadingKeys?.includes(noteKey(group)) ? 'Loading…' : noteLoadedKeys?.includes(unitNoteKey(group, unit)) || noteLoadedKeys?.includes(noteKey(group)) ? 'No recent activity note' : 'Not loaded') }}</span></div>
          <InventoryUnitActionLinks :item-id="unit.id" />
        </div>
      </div>
    </article>
    <nav v-if="groups.length > pageSize" class="flex items-center justify-end gap-2" aria-label="Inventory group pages">
      <button class="rounded border px-3 py-2" :disabled="page <= 1" @click="emit('update:page', page - 1)">Previous</button>
      <span class="text-sm">Page {{ page }} of {{ Math.ceil(groups.length / pageSize) }} · {{ groups.length }} groups</span>
      <button class="rounded border px-3 py-2" :disabled="page >= Math.ceil(groups.length / pageSize)" @click="emit('update:page', page + 1)">Next</button>
    </nav>
  </section>
</template>
