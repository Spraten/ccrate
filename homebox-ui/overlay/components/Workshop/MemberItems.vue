<script setup lang="ts">
  import { Button } from "@/components/ui/button";
  import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
  import { ChevronDown, ImageOff } from "lucide-vue-next";
  import type { WorkshopLoan } from "@/lib/workshop-loans";

  const props = defineProps<{ memberId: string; loans: WorkshopLoan[] | null; loading: boolean; error: string }>();
  const api = useUserApi();
  const open = ref(false), now = ref(Date.now()), failedImages = ref(new Set<string>());
  let timer: ReturnType<typeof setInterval> | null = null;
  const items = computed(() => (props.loans || []).filter(loan => loan.actor_id === props.memberId)
    .sort((a, b) => a.entity_name.localeCompare(b.entity_name)));
  watch(() => props.loans, () => { if (props.loans === null) open.value = false; });
  watch(open, value => { if (value) now.value = Date.now(); });
  onMounted(() => { timer = setInterval(() => { if (open.value) now.value = Date.now(); }, 60000); });
  onBeforeUnmount(() => { if (timer) clearInterval(timer); });
  function date(value?: string) { const parsed = Date.parse(value || ""); return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : "Checkout date unavailable"; }
  function elapsed(value?: string) {
    const parsed = Date.parse(value || "");
    if (!Number.isFinite(parsed)) return "Duration unavailable";
    const minutes = Math.max(0, Math.floor((now.value - parsed) / 60000));
    if (minutes < 1) return "Less than a minute";
    if (minutes < 60) return `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
    const hours = Math.floor(minutes / 60), days = Math.floor(hours / 24);
    return days ? `${days} ${days === 1 ? "day" : "days"}, ${hours % 24} hr` : `${hours} hr, ${minutes % 60} min`;
  }
  function image(item: WorkshopLoan) { return api.authURL(`/entities/${item.entity_id}/attachments/${item.thumbnailId || item.imageId}`); }
</script>

<template>
  <div class="min-w-44" data-testid="member-items">
    <span v-if="loading && loans === null" class="text-sm text-muted-foreground">Loading items…</span>
    <span v-else-if="error" class="text-sm text-muted-foreground">Items unavailable</span>
    <Popover v-else v-model:open="open">
      <PopoverTrigger as-child>
        <Button v-if="items.length" variant="outline" size="sm" :aria-label="items.length + (items.length === 1 ? ' item checked out' : ' items checked out')">
          {{ items.length }} {{ items.length === 1 ? 'item' : 'items' }} checked out<ChevronDown class="ml-2 size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" class="w-[min(24rem,calc(100vw-2rem))] p-0" aria-label="Checked-out item details">
        <div class="max-h-96 space-y-4 overflow-y-auto p-4">
          <h3 class="text-sm font-semibold">Checked-out items</h3>
          <div v-for="item in items" :key="item.entity_id" class="flex gap-3 border-t pt-3">
            <img v-if="item.imageId && !failedImages.has(item.entity_id)" :src="image(item)" :alt="'Preview of ' + item.entity_name" loading="lazy" class="size-16 shrink-0 rounded-md border object-contain" @error="failedImages = new Set([...failedImages, item.entity_id])" />
            <div v-else class="flex size-16 shrink-0 items-center justify-center rounded-md border bg-muted text-muted-foreground" role="img" :aria-label="'No photo for ' + item.entity_name"><ImageOff class="size-6" /></div>
            <div class="min-w-0 space-y-1 text-sm">
              <span v-if="item.unavailable" class="text-muted-foreground">{{ item.entity_name }}</span>
              <NuxtLink v-else :to="'/item/' + item.entity_id" class="font-medium hover:underline">{{ item.entity_name }}</NuxtLink>
              <p v-if="item.assetId" class="text-xs text-muted-foreground">{{ item.assetId }}</p>
              <p>Checked out: <time :datetime="item.checked_out_at">{{ date(item.checked_out_at) }}</time></p>
              <p>Out for: {{ elapsed(item.checked_out_at) }}</p>
              <NuxtLink v-if="!item.unavailable" :to="'/item/' + item.entity_id + '/loans'" class="inline-block text-xs underline">View loan history</NuxtLink>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
    <span v-if="!loading && !error && loans !== null && !items.length" class="text-sm text-muted-foreground">No items checked out</span>
  </div>
</template>
