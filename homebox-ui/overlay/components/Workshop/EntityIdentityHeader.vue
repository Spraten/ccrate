<script setup lang="ts">
import type { EntitySummary } from "@/lib/api/types/data-contracts";
const props = defineProps<{ entity: EntitySummary; kind: "item" | "location"; status?: string; locationPath?: string }>();
const api = useUserApi();
const imageId = computed(() => props.entity.thumbnailId || props.entity.imageId || "");
const imageSrc = computed(() => imageId.value ? api.authURL(`/entities/${props.entity.id}/attachments/${imageId.value}`) : "");
</script>
<template>
  <div class="flex min-w-0 items-center gap-4" data-testid="entity-identity-header">
    <img v-if="imageSrc" :src="imageSrc" :alt="entity.name" class="size-20 shrink-0 rounded-md border object-cover" />
    <div v-else class="flex size-20 shrink-0 items-center justify-center rounded-md border bg-muted text-sm text-muted-foreground">No photo</div>
    <div class="min-w-0">
      <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">{{ kind === "location" ? "Location" : "Item" }}</p>
      <h1 class="break-words text-2xl font-semibold">{{ entity.name }}</h1>
      <p v-if="status" class="text-sm text-muted-foreground">{{ status }}</p>
      <p v-if="locationPath" class="truncate text-sm text-muted-foreground">{{ locationPath }}</p>
    </div>
  </div>
</template>
