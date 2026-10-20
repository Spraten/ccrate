<script setup lang="ts">
  import BaseCard from "@/components/Base/Card.vue";
  import Subtitle from "@/components/global/Subtitle.vue";
  import { Button } from "@/components/ui/button";

  type CountMap = Record<string, number>;
  type LocationCount = { id: string | null; name: string; path: string; count: number };
  type HomeStatistics = {
    generated_at: string;
    totals: { items: number; locations: number; tags: number };
    condition_counts: CountMap;
    availability_counts: CountMap;
    location_counts: LocationCount[];
    attention_counts: { needs_attention: number; unreviewed: number; missing_photo: number; unassigned_location: number };
  };
  type Category = { key: string; label: string; count: number; tone: string; percent: number; offset: number };

  const workshop = useWorkshop();
  const { selectedId } = useCollections();
  const auth = useAuthContext();
  const summary = ref<HomeStatistics | null>(null);
  const loading = ref(true);
  const error = ref("");
  let revision = 0;
  let disposed = false;

  const conditionLabels = [
    ["Ready", "Ready", "primary"], ["Needs Attention", "Needs attention", "destructive"],
    ["Maintenance", "Maintenance", "accent"], ["Quarantined", "Quarantined", "foreground"],
    ["Archived", "Archived", "muted"], ["Retired", "Retired", "secondary"],
    ["Broken", "Broken", "destructive"], ["Trashed", "Trashed", "foreground"],
    ["Unreviewed", "Unreviewed", "muted"],
  ];
  const availabilityLabels = [
    ["available", "In stock (checked in)", "primary"],
    ["checked_out", "Checked out", "accent"],
    ["blocked", "Blocked / recovery", "destructive"],
    ["unknown", "Unknown", "muted"],
  ];
  const circumference = 2 * Math.PI * 42;

  function categories(counts: CountMap, labels: string[][]): Category[] {
    const total = summary.value?.totals.items || 0;
    let offset = 0;
    return labels.map(([key, label, tone]) => {
      const count = counts[key!] || 0;
      const percent = total ? count / total * 100 : 0;
      const category = { key: key!, label: label!, count, tone: tone!, percent, offset };
      offset += count;
      return category;
    });
  }

  const conditions = computed(() => categories(summary.value?.condition_counts || {}, conditionLabels));
  const availability = computed(() => categories(summary.value?.availability_counts || {}, availabilityLabels));
  const locations = computed(() => [...(summary.value?.location_counts || [])]
    .filter(row => row.count > 0 || (row.id === null && row.name === "Unassigned"))
    .sort((a, b) => b.count - a.count));
  const largestLocation = computed(() => Math.max(1, ...locations.value.map(row => row.count)));
  const updatedAt = computed(() => {
    const date = new Date(summary.value?.generated_at || "");
    return Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
  });
  const number = (count: number) => count.toLocaleString();
  const percentage = (value: number) => `${Math.round(value)}%`;

  async function load() {
    const current = ++revision;
    loading.value = true;
    error.value = "";
    summary.value = null;
    try {
      const result = await workshop.request<HomeStatistics>("home/statistics");
      if (!disposed && current === revision) summary.value = result;
    } catch (cause) {
      if (!disposed && current === revision) {
        const message = (cause as Error).message;
        error.value = message === "No confirmation received. Check Recovery before trying again."
          ? "Statistics request timed out. Refresh to try again."
          : message || "The summary is unavailable.";
      }
    } finally {
      if (!disposed && current === revision) loading.value = false;
    }
  }

  function refreshIfVisible() {
    if (document.visibilityState === "visible" && !loading.value) void load();
  }
  watch([selectedId, () => auth.user?.id], load, { immediate: true, flush: "sync" });
  onMounted(() => {
    window.addEventListener("focus", refreshIfVisible);
    document.addEventListener("visibilitychange", refreshIfVisible);
  });
  onBeforeUnmount(() => {
    disposed = true;
    revision++;
    window.removeEventListener("focus", refreshIfVisible);
    document.removeEventListener("visibilitychange", refreshIfVisible);
  });
</script>

<template>
  <section aria-labelledby="quick-statistics-heading">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div>
        <Subtitle id="quick-statistics-heading" class="mb-0">Quick Statistics</Subtitle>
        <p v-if="summary && updatedAt" class="text-xs text-muted-foreground">Updated {{ updatedAt }}</p>
      </div>
      <Button variant="outline" size="sm" :disabled="loading" @click="load">Refresh statistics</Button>
    </div>

    <BaseCard v-if="loading">
      <p role="status" class="p-5 text-sm text-muted-foreground">Loading statistics…</p>
    </BaseCard>
    <BaseCard v-else-if="error || !summary">
      <div role="alert" class="space-y-3 p-5 text-sm">
        <p class="text-destructive">Statistics are unavailable. {{ error }}</p>
        <Button variant="outline" size="sm" @click="load">Try again</Button>
      </div>
    </BaseCard>
    <template v-else>
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-7">
        <div v-for="stat in [
          { label: 'Total Items', count: summary.totals.items },
          { label: 'Total Locations', count: summary.totals.locations },
          { label: 'Total Tags', count: summary.totals.tags },
          { label: 'Needs attention', count: summary.attention_counts.needs_attention },
          { label: 'Unreviewed', count: summary.attention_counts.unreviewed },
          { label: 'No photo', count: summary.attention_counts.missing_photo },
          { label: 'Unassigned', count: summary.attention_counts.unassigned_location },
        ]" :key="stat.label" class="min-w-0 rounded-lg border bg-card p-3 text-card-foreground shadow-sm">
          <p class="text-sm text-muted-foreground">{{ stat.label }}</p>
          <p class="mt-1 text-2xl font-semibold tabular-nums">{{ number(stat.count) }}</p>
        </div>
      </div>

      <BaseCard v-if="summary.totals.items === 0" class="mt-4">
        <p class="p-5 text-sm text-muted-foreground">No equipment records in this collection yet. The breakdown will appear when items are added.</p>
      </BaseCard>
      <div v-else class="mt-4 space-y-4">
        <h3 class="text-lg font-medium">Inventory breakdown</h3>
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <BaseCard v-for="chart in [
            { title: 'Condition', rows: conditions },
            { title: 'Availability', rows: availability },
          ]" :key="chart.title">
            <div class="p-4 sm:p-5">
              <h4 class="mb-4 font-medium">{{ chart.title }}</h4>
              <div class="flex flex-col items-start gap-4 sm:flex-row sm:items-center">
                <div class="relative size-36 shrink-0">
                  <svg viewBox="0 0 100 100" class="size-full -rotate-90" aria-hidden="true" focusable="false">
                    <circle cx="50" cy="50" r="42" fill="none" class="stroke-muted" stroke-width="12" />
                    <circle v-for="row in chart.rows.filter(category => category.count > 0)" :key="row.key"
                      cx="50" cy="50" r="42" fill="none" :class="`stat-tone-${row.tone}`"
                      stroke-width="12" :stroke-dasharray="`${row.percent / 100 * circumference} ${circumference}`"
                      :stroke-dashoffset="-row.offset / summary.totals.items * circumference" />
                  </svg>
                  <div class="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
                    <strong class="text-xl tabular-nums">{{ number(summary.totals.items) }}</strong>
                    <span class="text-xs text-muted-foreground">items</span>
                  </div>
                </div>
                <ul class="w-full min-w-0 space-y-2 text-sm" :aria-label="`${chart.title} counts`">
                  <li v-for="row in chart.rows" :key="row.key" class="flex min-w-0 items-start gap-2">
                    <span aria-hidden="true" class="mt-1 size-2.5 shrink-0 rounded-full" :class="`stat-swatch-${row.tone}`" />
                    <span class="min-w-0 flex-1 break-words">{{ row.label }}</span>
                    <span class="shrink-0 tabular-nums">{{ number(row.count) }} <span class="text-muted-foreground">({{ percentage(row.percent) }})</span></span>
                  </li>
                </ul>
              </div>
            </div>
          </BaseCard>
        </div>

        <BaseCard>
          <div class="p-4 sm:p-5">
            <h4 class="font-medium">Storage locations</h4>
            <p class="mb-4 text-sm text-muted-foreground">Each item counts once at its direct storage location. Other groups the remaining locations.</p>
            <ol class="space-y-3">
              <li v-for="row in locations" :key="row.id || row.name" class="min-w-0">
                <div class="mb-1 flex min-w-0 items-start justify-between gap-3 text-sm">
                  <span class="min-w-0 break-words" :title="row.path">{{ row.path }}</span>
                  <span class="shrink-0 tabular-nums">{{ number(row.count) }} <span class="text-muted-foreground">({{ percentage(row.count / summary.totals.items * 100) }})</span></span>
                </div>
                <div class="h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                  <div class="h-full rounded-full bg-primary" :style="{ width: `${row.count / largestLocation * 100}%` }" />
                </div>
              </li>
            </ol>
          </div>
        </BaseCard>
      </div>
    </template>
  </section>
</template>

<style scoped>
  .stat-tone-primary { stroke: hsl(var(--primary)); }
  .stat-tone-accent { stroke: hsl(var(--accent)); }
  .stat-tone-destructive { stroke: hsl(var(--destructive)); }
  .stat-tone-foreground { stroke: hsl(var(--foreground)); }
  .stat-tone-muted { stroke: hsl(var(--muted-foreground)); }
  .stat-tone-secondary { stroke: hsl(var(--secondary-foreground)); }
  .stat-swatch-primary { background: hsl(var(--primary)); }
  .stat-swatch-accent { background: hsl(var(--accent)); }
  .stat-swatch-destructive { background: hsl(var(--destructive)); }
  .stat-swatch-foreground { background: hsl(var(--foreground)); }
  .stat-swatch-muted { background: hsl(var(--muted-foreground)); }
  .stat-swatch-secondary { background: hsl(var(--secondary-foreground)); }
</style>
