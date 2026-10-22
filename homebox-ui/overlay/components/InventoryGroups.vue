<script setup lang="ts">
import { inventoryNoteRequestKey } from '@/lib/child-item-groups.js';
type Unit = Record<string, any> & { id: string; name?: string; displayId?: string; status?: string; storagePath?: string; thumbnail?: { entity_id: string; attachment_id: string } | null };
type Group = { key: string; name: string; items: Unit[]; recordCount: number; nativeQuantity: number; statusCounts: Record<string, number>; thumbnail: Unit['thumbnail']; locationSummary: string };
const props = defineProps<{ groups: Group[]; page: number; pageSize: number; recentNotes?: Record<string, any>; noteLoadingKeys?: string[]; noteLoadedKeys?: string[]; selectedId?: string }>();
const emit = defineEmits<{ 'update:page': [page: number]; 'load-notes': [request: { key: string; entityIds: string[]; refresh?: boolean }]; 'refresh-items': [] }>();
const api = useUserApi();
const route = useRoute();
const router = useRouter();
const itemActions = useItemActions();
const actionStatuses = reactive(new Map<string, any>());
const expanded = ref(new Set<string>());
const visible = computed(() => props.groups.slice((props.page - 1) * props.pageSize, props.page * props.pageSize));
const selectedId = computed(() => props.selectedId || (typeof route.query.selected === 'string' ? route.query.selected : ''));
const selected = computed(() => props.groups.flatMap(group => group.items).find(item => item.id === selectedId.value));
const selectedGroup = computed(() => props.groups.find(group => group.items.some(item => item.id === selectedId.value)));
const isMobileDetail = ref(false);
const selectedHeading = ref<HTMLElement | null>(null);
const rowRefs = new Map<string, HTMLElement>();
function setRowRef(id: string, element: Element | null) { if (element instanceof HTMLElement) rowRefs.set(id, element); else rowRefs.delete(id); }
let reconciledSelectionId = '';
watch(selectedId, id => { isMobileDetail.value = !!id; }, { immediate: true });
watch([selectedId, () => props.groups, () => props.pageSize], ([id]) => {
  if (!id) { reconciledSelectionId = ''; return; }
  if (id === reconciledSelectionId) return;
  const index = props.groups.findIndex(group => group.items.some(item => item.id === id));
  if (index < 0) return;
  reconciledSelectionId = id;
  const targetPage = Math.floor(index / Math.max(1, props.pageSize)) + 1;
  if (targetPage !== props.page) emit('update:page', targetPage);
  const group = props.groups[index]!;
  if (!expanded.value.has(group.key)) { expanded.value = new Set(expanded.value).add(group.key); emit('load-notes', { key: group.key, entityIds: group.items.map(item => item.id) }); }
}, { immediate: true });
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
  for (const unit of group.items) { const raw = unitStatus(unit); const key = raw === 'checkedOut' ? 'checked_out' : raw; counts[key in counts ? key as keyof typeof counts : 'unknown']++; }
  return counts;
}
watch(itemActions.changed, async result => {
  if (!result || result.kind === 'cart') return;
  const loaded = new Set(props.groups.flatMap(group => group.items.map(item => item.id)));
  for (const id of result.itemIds) {
    if (!loaded.has(id)) continue;
    try { actionStatuses.set(id, await itemActions.loadStatus(id, true)); } catch { actionStatuses.delete(id); }
    const group = props.groups.find(row => row.items.some(item => item.id === id));
    if (group && expanded.value.has(group.key)) emit('load-notes', { key: group.key, entityIds: [id], refresh: true });
  }
  emit('refresh-items');
});
function photoUrl(photo: Unit['thumbnail']) { return photo ? api.authURL(`/entities/${encodeURIComponent(photo.entity_id)}/attachments/${encodeURIComponent(photo.attachment_id)}`) : ''; }
function noteTime(value?: string | null) {
  const instant = Date.parse(value || '');
  return Number.isFinite(instant) ? new Date(instant).toLocaleString() : 'Time unavailable';
}
function noteAttribution(note: any) {
  return note?.note_state === 'edited' || note?.note_current_text_attribution === 'unknown'
    ? 'Author unknown (edited text)' : note?.author || 'Author unknown';
}
async function selectUnit(unit: Unit) {
  await router.push({ query: { ...route.query, selected: unit.id } });
  if (typeof window !== 'undefined' && window.matchMedia('(max-width: 1023px)').matches) {
    await nextTick();
    selectedHeading.value?.focus();
  }
  const group = props.groups.find(row => row.items.some(item => item.id === unit.id));
  if (group && !expanded.value.has(group.key)) { expanded.value = new Set(expanded.value).add(group.key); emit('load-notes', { key: group.key, entityIds: group.items.map(item => item.id) }); }
}
async function backToResults() {
  isMobileDetail.value = false;
  const id = selectedId.value;
  const query = { ...route.query }; delete query.selected;
  await router.push({ query });
  await nextTick();
  if (id) rowRefs.get(id)?.focus();
}
</script>

<template>
  <section class="grid gap-4 lg:grid-cols-[minmax(18rem,0.9fr)_minmax(24rem,1.3fr)]" aria-label="Grouped inventory">
    <div class="space-y-3" :class="{ 'hidden lg:block': isMobileDetail }">
      <article v-for="group in visible" :key="group.key" class="overflow-hidden rounded-lg border bg-card">
        <button class="flex w-full items-center gap-3 p-3 text-left" :aria-expanded="expanded.has(group.key)" @click="toggle(group)">
          <img v-if="group.thumbnail" :src="photoUrl(group.thumbnail)" alt="" class="size-14 rounded object-cover" />
          <div v-else class="flex size-14 shrink-0 items-center justify-center rounded bg-muted text-xs text-muted-foreground">No photo</div>
          <div class="min-w-0 flex-1"><strong class="block truncate">{{ group.name }}</strong><span class="block truncate text-sm text-muted-foreground">{{ group.locationSummary }}</span><span class="block text-xs text-muted-foreground">{{ groupCounts(group).available }} available · {{ groupCounts(group).checked_out }} checked out · {{ groupCounts(group).blocked }} blocked · {{ groupCounts(group).archived }} archived · {{ groupCounts(group).unknown }} unknown</span></div>
          <span class="whitespace-nowrap font-semibold">×{{ group.recordCount }} <span aria-hidden="true">{{ expanded.has(group.key) ? '⌄' : '›' }}</span></span>
        </button>
        <div v-if="expanded.has(group.key)" class="divide-y border-t">
          <div v-for="unit in group.items" :key="unit.id" class="flex flex-wrap items-center gap-3 p-3" :class="selectedId === unit.id ? 'bg-accent text-accent-foreground' : ''">
            <img v-if="unit.thumbnail" :src="photoUrl(unit.thumbnail)" alt="" class="size-10 rounded object-cover" />
            <div class="min-w-0 flex-1"><button class="block max-w-full truncate text-left font-semibold underline-offset-4 hover:underline focus-visible:underline" :aria-current="selectedId === unit.id ? 'true' : undefined" :ref="element => setRowRef(unit.id, element as Element | null)" @click="selectUnit(unit)">{{ unit.name || 'Unnamed item' }}</button><span class="block text-sm text-muted-foreground">{{ unit.displayId || 'No assigned ID' }} · {{ statusLabel(unitStatus(unit)) }}</span><span class="block truncate text-xs text-muted-foreground">{{ unit.storagePath || 'Location unknown' }} · Serial {{ unit.serialNumber || 'unknown' }} · {{ Number(unit.quantity) || 0 }} native quantity</span><template v-if="recentNotes?.[unit.id]"><span class="block truncate text-xs text-muted-foreground">Recent note: {{ recentNotes[unit.id].text }}</span><span class="block text-xs text-muted-foreground">{{ noteTime(recentNotes[unit.id].created_at) }} · {{ noteAttribution(recentNotes[unit.id]) }}</span></template><span v-else class="block text-xs text-muted-foreground">Recent note: {{ noteLoadingKeys?.includes(unitNoteKey(group, unit)) || noteLoadingKeys?.includes(noteKey(group)) ? 'Loading…' : noteLoadedKeys?.includes(unitNoteKey(group, unit)) || noteLoadedKeys?.includes(noteKey(group)) ? 'No recent activity note' : 'Not loaded' }}</span></div>
            <InventoryUnitActionLinks :item-id="unit.id" />
          </div>
        </div>
      </article>
      <nav v-if="groups.length > pageSize" class="flex items-center justify-end gap-2" aria-label="Inventory group pages">
        <button class="rounded border px-3 py-2" :disabled="page <= 1" @click="emit('update:page', page - 1)">Previous</button><span class="text-sm">Page {{ page }} of {{ Math.ceil(groups.length / pageSize) }} · {{ groups.length }} groups</span><button class="rounded border px-3 py-2" :disabled="page >= Math.ceil(groups.length / pageSize)" @click="emit('update:page', page + 1)">Next</button>
      </nav>
    </div>
    <aside class="min-h-64 rounded-lg border bg-card p-4 lg:p-6" :class="{ 'hidden lg:block': !isMobileDetail, 'min-h-[calc(100dvh-2rem)] lg:min-h-64': isMobileDetail }" aria-label="Selected inventory details">
      <button v-if="isMobileDetail" class="mb-4 rounded border px-3 py-2 lg:hidden" @click="backToResults">← Back to results</button>
      <template v-if="selected">
        <div class="flex flex-wrap items-start gap-4">
          <img v-if="selected.thumbnail" :src="photoUrl(selected.thumbnail)" alt="" class="size-24 rounded object-cover" />
          <div v-else class="flex size-24 items-center justify-center rounded bg-muted text-sm text-muted-foreground">No photo</div>
          <div class="min-w-0 flex-1"><p class="text-sm text-muted-foreground">{{ selected.displayId || selected.id }} · {{ statusLabel(unitStatus(selected)) }}</p><h2 ref="selectedHeading" tabindex="-1" class="mt-1 text-xl font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring">{{ selected.name || 'Unnamed item' }}</h2><p class="mt-1 text-sm text-muted-foreground">{{ selected.storagePath || selectedGroup?.locationSummary || 'Location unknown' }}</p></div>
        </div>
        <dl class="mt-5 grid grid-cols-2 gap-4 border-t pt-4 text-sm"><div><dt class="text-muted-foreground">Quantity</dt><dd class="font-medium">{{ Number(selected?.quantity) || 0 }}</dd></div><div><dt class="text-muted-foreground">Serial number</dt><dd class="font-medium">{{ selected?.serialNumber || 'Not set' }}</dd></div><div><dt class="text-muted-foreground">Group</dt><dd class="font-medium">{{ selectedGroup?.name || '—' }}</dd></div><div><dt class="text-muted-foreground">Recent note</dt><dd class="font-medium whitespace-pre-wrap">{{ recentNotes?.[selected?.id || '']?.text || (noteLoadedKeys?.some(key => key.includes(selected?.id || '')) ? 'No recent activity note' : 'Not loaded') }}</dd><dd v-if="recentNotes?.[selected?.id || '']" class="mt-1 text-xs text-muted-foreground">{{ noteTime(recentNotes[selected?.id || ''].created_at) }} · {{ noteAttribution(recentNotes[selected?.id || '']) }}</dd></div></dl>
        <div class="mt-5 flex flex-wrap gap-2"><NuxtLink class="inline-flex items-center rounded-md bg-primary px-4 py-2 text-primary-foreground" :to="`/item/${encodeURIComponent(selected.id)}`">Open full details</NuxtLink></div>
      </template>
      <div v-else class="flex min-h-52 items-center justify-center text-center text-sm text-muted-foreground"><div><strong class="block text-base text-foreground">Select an item</strong><span class="mt-1 block">Choose an inventory row to see its details here.</span></div></div>
    </aside>
  </section>
</template>
