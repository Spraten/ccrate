<script setup lang="ts">
  import { Input } from "@/components/ui/input";
  import { Label } from "@/components/ui/label";
  import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
  import { recentItemNotes } from "@/lib/item-activity-notes.js";
  import type { WorkshopHistoryRow } from "@/lib/workshop-loans";

  const props = defineProps<{ itemId: string }>();
  const workshop = useWorkshop();
  const itemActions = useItemActions();
  const { selectedId } = useCollections();
  const expanded = ref(false);
  const rows = ref<WorkshopHistoryRow[]>([]);
  const loading = ref(false);
  const error = ref("");
  const canAddNote = ref(false);
  const noteFilter = ref("");
  const personFilter = ref("");
  const actionFilter = ref<"all" | "check_out" | "return" | "add_note">("all");
  const fromLocal = ref("");
  const toLocal = ref("");
  let revision = 0;

  const scope = computed(() => [props.itemId, selectedId.value || "",
    workshop.context.value?.user.id || "", workshop.context.value?.group.id || ""].join("|"));

  const personOptions = computed(() => {
    const unique = new Map<string, WorkshopHistoryRow>();
    for (const row of rows.value) if (row.actor_id && !unique.has(row.actor_id)) unique.set(row.actor_id, row);
    return [...unique.values()].sort((a, b) => personLabel(a).localeCompare(personLabel(b)));
  });
  const itemNotes = computed(() => recentItemNotes(rows.value, props.itemId, Infinity));

  function shortId(value?: string) { return value ? value.replaceAll("-", "").slice(0, 8).toUpperCase() : "unknown"; }
  function personName(row: WorkshopHistoryRow) {
    return row.actor_id === "00000000-0000-0000-0000-000000000000" ? "Unidentified returner" : row.actor || "Former C-Crate member";
  }
  function personLabel(row: WorkshopHistoryRow) {
    const name = personName(row);
    const duplicate = rows.value.some(other => other.actor_id !== row.actor_id && personName(other) === name);
    return name === "Unidentified returner" ? name
      : name === "Former C-Crate member" || duplicate ? `${name} · ${shortId(row.actor_id)}` : name;
  }
  function actionLabel(row: WorkshopHistoryRow) {
    const known: Record<string, string> = {
      check_out: "Check-out", return: "Check-in", add_note: "Item note",
      print_label: "Label print", print_badge: "Badge print", report_problem: "Problem report",
      review_condition: "Condition review", complete_maintenance: "Maintenance review",
      create_asset: "Equipment created", create_location: "Location created",
      create_template: "Template created", create_type: "Equipment type created",
      register_code: "Code registered",
    };
    return known[row.action] || row.action.replaceAll("_", " ");
  }
  function recordedTime(row: WorkshopHistoryRow) {
    return row.status === "completed" && row.confirmed_at ? row.confirmed_at : row.created_at;
  }
  function timeMeaning(row: WorkshopHistoryRow) {
    return row.status === "completed" && row.confirmed_at ? "Confirmed" : "Requested";
  }
  function formatTime(value?: string) {
    const instant = Date.parse(value || "");
    return Number.isFinite(instant) ? new Date(instant).toLocaleString() : "Time unavailable";
  }
  function noteAuthor(note: { author?: string | null; note_state?: string; note_current_text_attribution?: string }) {
    return note.note_state === "edited" || note.note_current_text_attribution === "unknown"
      ? "Author unknown (edited text)" : note.author || "Author unknown";
  }
  function noteKind(kind = "note") {
    return kind === "checkout" ? "Checkout note" : kind === "return" ? "Return note" : "Item note";
  }
  function openNote(event: MouseEvent) {
    void itemActions.open({ kind: "note", itemId: props.itemId, source: "item-row" }, event.currentTarget as HTMLElement);
  }
  function parseLocalDateTime(value: string): number | null {
    if (!value) return null;
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value);
    if (!match) return Number.NaN;
    const [, year, month, day, hour, minute, second = "0"] = match;
    const date = new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second));
    if (date.getFullYear() !== Number(year) || date.getMonth() !== Number(month) - 1
      || date.getDate() !== Number(day) || date.getHours() !== Number(hour)
      || date.getMinutes() !== Number(minute) || date.getSeconds() !== Number(second)) return Number.NaN;
    return date.getTime();
  }

  const rangeError = computed(() => {
    const from = parseLocalDateTime(fromLocal.value), to = parseLocalDateTime(toLocal.value);
    if (Number.isNaN(from) || Number.isNaN(to)) return "Enter valid local date and time values.";
    if (from !== null && to !== null && from > to) return "The start of the date and time range must be before its end.";
    return "";
  });

  function noteText(row: WorkshopHistoryRow) {
    const text = [row.note_text || "", ...(row.return_notes || []).map(note => note.text || ""), ...(row.checkout_notes || []).filter(note => note.entity_id === props.itemId).map(note => note.text || "")];
    return text.join("\n");
  }
  const filteredRows = computed(() => {
    if (rangeError.value) return [];
    const query = noteFilter.value.trim().toLocaleLowerCase();
    const from = parseLocalDateTime(fromLocal.value), to = parseLocalDateTime(toLocal.value);
    return rows.value.filter(row => {
      if (actionFilter.value !== "all" && row.action !== actionFilter.value) return false;
      if (personFilter.value && row.actor_id !== personFilter.value) return false;
      if (query && !noteText(row).toLocaleLowerCase().includes(query)) return false;
      if (from === null && to === null) return true;
      const instant = Date.parse(recordedTime(row));
      if (!Number.isFinite(instant)) return false;
      return (from === null || instant >= from) && (to === null || instant <= to);
    });
  });

  function returnNoteAuthor(note: { author?: string }) { return note.author || "Recorded returner"; }
  function priorBorrowers(row: WorkshopHistoryRow) {
    return row.previous_borrowers || [];
  }
  function priorBorrowerLabel(person: { user_id?: string; name?: string; name_snapshot?: string }) {
    const recorded = person.user_id ? rows.value.find(row => row.actor_id === person.user_id) : undefined;
    const name = recorded ? personName(recorded) : person.name_snapshot || person.name || "Recorded member";
    return person.user_id ? `${name} · ${shortId(person.user_id)}` : name;
  }

  async function load() {
    const currentRevision = ++revision;
    const expectedScope = scope.value;
    const itemId = props.itemId;
    loading.value = true;
    error.value = "";
    try {
      const [result, status] = await Promise.all([
        workshop.request<WorkshopHistoryRow[]>(`history?entity=${encodeURIComponent(itemId)}`),
        itemActions.loadStatus(itemId).catch(() => null),
      ]);
      if (currentRevision !== revision || !expanded.value || expectedScope !== scope.value) return;
      rows.value = Array.isArray(result) ? result : [];
      canAddNote.value = !!status?.can_add_note;
    } catch (cause) {
      if (currentRevision === revision && expanded.value && expectedScope === scope.value) {
        error.value = (cause as Error).message;
      }
    } finally {
      if (currentRevision === revision && expectedScope === scope.value) loading.value = false;
    }
  }

  function toggleDisclosure(event: Event) {
    expanded.value = (event.currentTarget as HTMLDetailsElement).open;
    if (expanded.value) void load();
    else { revision++; loading.value = false; }
  }

  watch(itemActions.changed, result => {
    if (expanded.value && result?.kind !== "cart" && result?.itemIds.includes(props.itemId)) void load();
  });

  watch(scope, () => {
    revision++;
    rows.value = [];
    canAddNote.value = false;
    error.value = "";
    noteFilter.value = "";
    personFilter.value = "";
    actionFilter.value = "all";
    fromLocal.value = "";
    toLocal.value = "";
    if (expanded.value) void load();
  }, { flush: "sync" });

  onBeforeUnmount(() => {
    revision++;
    rows.value = [];
  });
</script>

<template>
  <details data-testid="item-log" class="rounded-lg border bg-card" @toggle="toggleDisclosure">
    <summary class="cursor-pointer px-4 py-3 text-base font-medium">Log &amp; notes</summary>
    <div class="space-y-3 border-t p-3">
      <details data-testid="item-notes" class="rounded-md border">
        <summary class="cursor-pointer px-3 py-2 font-medium">Notes <span class="text-sm font-normal text-muted-foreground">({{ itemNotes.length }})</span></summary>
        <div class="space-y-3 border-t p-3">
          <button v-if="canAddNote" type="button" class="rounded-md border px-3 py-2 text-sm" @click="openNote">Add note</button>
          <p v-if="!itemNotes.length" class="text-sm text-muted-foreground">No checkout, return, or item notes recorded.</p>
          <ol v-else class="divide-y">
            <li v-for="(note, index) in itemNotes" :key="index" class="space-y-1 py-2 first:pt-0 last:pb-0">
              <p class="whitespace-pre-wrap text-sm">{{ note.text }}</p>
              <p class="text-xs text-muted-foreground">{{ noteKind(note.kind) }} · <time v-if="note.created_at" :datetime="note.created_at || ''">{{ formatTime(note.created_at) }}</time><span v-else>Time unavailable</span> · {{ noteAuthor(note) }}</p>
            </li>
          </ol>
        </div>
      </details>
      <p class="text-sm text-muted-foreground">Filters apply to the loaded companion records (up to 100 newest requests); older activity and unjournaled native changes are not included.</p>
      <p class="text-sm"><NuxtLink :to="`/item/${itemId}/maintenance`" class="underline">Open the native maintenance Log</NuxtLink> for legacy maintenance entries.</p>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div class="space-y-1.5">
          <Label for="item-log-note-filter">Filter note text</Label>
          <Input id="item-log-note-filter" v-model="noteFilter" type="search" placeholder="Find note text" />
        </div>
        <div class="space-y-1.5">
          <Label for="item-log-person-filter">Person</Label>
          <select id="item-log-person-filter" v-model="personFilter" class="h-10 w-full rounded-md border bg-background px-3 text-sm">
            <option value="">All people</option>
            <option v-for="person in personOptions" :key="person.actor_id" :value="person.actor_id">{{ personLabel(person) }}</option>
          </select>
        </div>
        <div class="space-y-1.5">
          <Label for="item-log-action-filter">Action</Label>
          <select id="item-log-action-filter" v-model="actionFilter" class="h-10 w-full rounded-md border bg-background px-3 text-sm">
            <option value="all">All actions</option>
            <option value="check_out">Check-out</option>
            <option value="return">Check-in</option>
            <option value="add_note">Item note</option>
          </select>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div class="space-y-1.5">
            <Label for="item-log-from">From (local)</Label>
            <Input id="item-log-from" v-model="fromLocal" type="datetime-local" />
          </div>
          <div class="space-y-1.5">
            <Label for="item-log-to">To (local)</Label>
            <Input id="item-log-to" v-model="toLocal" type="datetime-local" />
          </div>
        </div>
      </div>
      <p v-if="rangeError" role="alert" class="text-sm text-destructive">{{ rangeError }}</p>
      <p v-if="loading" role="status" class="text-sm text-muted-foreground">Loading companion history…</p>
      <p v-else-if="error" role="alert" class="text-sm text-destructive">{{ error }} <button class="underline" @click="load">Reload</button></p>
      <p v-else-if="!filteredRows.length" class="text-sm text-muted-foreground">No matches in loaded history.</p>
      <div v-else class="overflow-x-auto">
        <Table class="min-w-[760px]">
          <TableHeader>
            <TableRow><TableHead>Action</TableHead><TableHead>Person</TableHead><TableHead>Time</TableHead><TableHead>Notes</TableHead></TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="row in filteredRows" :key="`${row.source}:${row.id}`">
              <TableCell class="align-top">
                <span class="block font-medium">{{ actionLabel(row) }}</span>
                <span class="text-xs text-muted-foreground">{{ row.status }}</span>
              </TableCell>
              <TableCell class="align-top">
                <span>{{ personLabel(row) }}</span>
                <span v-if="row.action === 'add_note' && row.note_author" class="block text-xs text-muted-foreground">Saved author: {{ row.note_author }}</span>
                <span v-if="row.action === 'return'" class="mt-1 block text-xs text-muted-foreground">
                  Prior borrower: {{ priorBorrowers(row).length ? priorBorrowers(row).map(priorBorrowerLabel).join(', ') : 'not recorded' }}
                </span>
              </TableCell>
              <TableCell class="min-w-40 align-top">
                <span class="block text-xs text-muted-foreground">{{ timeMeaning(row) }}</span>
                <time :datetime="recordedTime(row)">{{ formatTime(recordedTime(row)) }}</time>
              </TableCell>
              <TableCell class="min-w-64 align-top">
                <template v-if="row.action === 'add_note'">
                  <p v-if="typeof row.note_text === 'string'" class="whitespace-pre-wrap">{{ row.note_text }}</p>
                  <p v-else class="text-sm text-muted-foreground">{{ row.note_state === 'unavailable' ? 'Item note text is unavailable in C-Crate.' : `Item note is ${row.status}; its text is not available.` }}</p>
                  <p v-if="row.note_state === 'edited'" class="mt-1 text-xs text-muted-foreground">Current native text was edited; current-text attribution is unknown.</p>
                </template>
                <div v-else-if="row.return_notes?.length" class="space-y-2">
                  <div v-for="(note, index) in row.return_notes" :key="`${row.id}:return-note:${index}`">
                    <p class="whitespace-pre-wrap">{{ note.text }}</p>
                    <p class="text-xs text-muted-foreground">{{ returnNoteAuthor(note) }}</p>
                  </div>
                </div>
                <div v-else-if="row.checkout_notes?.some(note => note.entity_id === itemId)" class="space-y-2">
                  <div v-for="(note, index) in row.checkout_notes.filter(note => note.entity_id === itemId)" :key="`${row.id}:checkout-note:${index}`">
                    <p class="whitespace-pre-wrap">{{ note.text }}</p>
                    <p class="text-xs text-muted-foreground">Checkout note · {{ note.author }} · {{ formatTime(note.created_at) }}</p>
                  </div>
                </div>
                <span v-else class="text-muted-foreground">—</span>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </div>
  </details>
</template>
