<script setup lang="ts">
import ItemQuickActions from '@/components/Workshop/ItemQuickActions.vue';
defineProps<{ itemId: string }>();
</script>

<template>
  <div class="flex flex-wrap items-center gap-2" :data-native-item-id="itemId">
    <ItemQuickActions :item-id="itemId" compact />
    <NuxtLink class="rounded border px-3 py-2 text-sm" :to="`/item/${encodeURIComponent(itemId)}`">Open item</NuxtLink>
  </div>
</template>
