<script setup lang="ts">
  import BaseCard from "@/components/Base/Card.vue";
  import Subtitle from "@/components/global/Subtitle.vue";
  import { Badge } from "@/components/ui/badge";
  import { Button } from "@/components/ui/button";
  import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
  import { RefreshCw } from "lucide-vue-next";
  import type { WorkshopLoan } from "@/lib/workshop-loans";

  const workshop = useWorkshop();
  const { selectedId } = useCollections();
  const loans = ref<WorkshopLoan[] | null>(null);
  const loading = ref(true);
  const error = ref("");
  let generation = 0;
  let disposed = false;
  let timer: ReturnType<typeof setInterval> | null = null;

  async function load() {
    const revision = ++generation;
    loading.value = true;
    loans.value = null;
    error.value = "";
    try {
      const rows = await workshop.request<WorkshopLoan[]>("loans");
      if (!disposed && revision === generation) {
        loans.value = [...rows].sort((a, b) => a.entity_name.localeCompare(b.entity_name));
      }
    } catch (cause) {
      if (!disposed && revision === generation) error.value = (cause as Error).message;
    } finally {
      if (!disposed && revision === generation) loading.value = false;
    }
  }

  function refreshIfVisible() { if (document.visibilityState === "visible" && !loading.value) void load(); }
  watch(selectedId, load, { immediate: true, flush: "sync" });
  onMounted(() => {
    window.addEventListener("focus", refreshIfVisible);
    document.addEventListener("visibilitychange", refreshIfVisible);
    timer = setInterval(refreshIfVisible, 30000);
  });
  onBeforeUnmount(() => {
    disposed = true; generation++; loans.value = null;
    if (timer) clearInterval(timer);
    window.removeEventListener("focus", refreshIfVisible);
    document.removeEventListener("visibilitychange", refreshIfVisible);
  });
</script>

<template>
  <section aria-labelledby="checked-out-items-heading" data-testid="checked-out-items">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <Subtitle id="checked-out-items-heading" class="mb-0">Checked-out items</Subtitle>
        <Badge v-if="loans !== null" variant="outline" role="status" :aria-label="loans.length + ' checked out'">{{ loans.length }} checked out</Badge>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="icon" aria-label="Refresh checked-out items" :disabled="loading" @click="load"><RefreshCw class="size-4" :class="{ 'animate-spin': loading }" /></Button>
        <Button as-child variant="outline" size="sm"><NuxtLink to="/workshop/loans">View all loans</NuxtLink></Button>
      </div>
    </div>
    <BaseCard>
      <p v-if="loading" role="status" class="p-4 text-sm text-muted-foreground">Loading checked-out items…</p>
      <div v-else-if="error" role="alert" class="space-y-2 p-4 text-sm"><p class="text-destructive">Could not load checked-out items. {{ error }}</p><Button variant="outline" size="sm" @click="load">Try again</Button></div>
      <p v-else-if="!loans?.length" class="p-4 text-sm text-muted-foreground">No items are currently checked out in this collection.</p>
      <Table v-else>
        <TableHeader><TableRow><TableHead>Item</TableHead><TableHead>Borrower</TableHead><TableHead class="text-right">Loan details</TableHead></TableRow></TableHeader>
        <TableBody>
          <TableRow v-for="loan in loans" :key="loan.entity_id">
            <TableCell class="min-w-40">
              <span v-if="loan.unavailable" class="text-muted-foreground">{{ loan.entity_name }}</span>
              <NuxtLink v-else :to="'/item/' + loan.entity_id" class="font-medium hover:underline">{{ loan.entity_name }}</NuxtLink>
              <span v-if="loan.assetId" class="mt-1 block text-xs text-muted-foreground">{{ loan.assetId }}</span>
              <span v-if="loan.unavailable" class="mt-1 block text-xs text-muted-foreground">The item record is unavailable. Review this loan before changing it.</span>
            </TableCell>
            <TableCell>{{ loan.borrower }}</TableCell>
            <TableCell class="text-right"><Button v-if="!loan.unavailable" as-child variant="outline" size="sm"><NuxtLink :to="'/item/' + loan.entity_id + '/loans'" :aria-label="'View loan for ' + loan.entity_name">View loan</NuxtLink></Button></TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </BaseCard>
  </section>
</template>
