<script setup lang="ts">
  definePageMeta({ middleware: ["auth"] });
  const route = useRoute();
  const paths: Record<string, string> = { people: "/collection/members", equipment: "/items", overview: "/home", workshop: "/workshop/map" };
  const oldPage = route.hash.slice(1);
  await navigateTo(paths[oldPage] || (["loans", "checkout-cart", "imports", "labels", "recovery", "system", "equipment-ids"].includes(oldPage) ? `/workshop/${oldPage}` : "/workshop/loans"), { replace: true });
</script>
<template><div /></template>
