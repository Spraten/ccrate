<script setup lang="ts">
  import ItemLoans from "@/components/Workshop/ItemLoans.vue";
  definePageMeta({ middleware: ["auth"] });
  const route = useRoute();
</script>
<template><ItemLoans :item-id="String(route.params.id)" activity-mode="details" /></template>
