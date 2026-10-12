<script setup lang="ts">
  import { Button } from "@/components/ui/button";
  const props = defineProps<{ device: "printer" | "camera" }>();
  const workshop = useWorkshop();
  const checking = ref(false), result = ref<{ message: string; steps: string[] } | null>(null);
  let disposed = false;
  onBeforeUnmount(() => { disposed = true; });
  async function reconnect() {
    checking.value = true; result.value = null;
    try {
      const next = await workshop.request<{ message: string; steps: string[] }>("hardware/reconnect", { device: props.device });
      if (!disposed) result.value = next;
    } catch (error) { if (!disposed) result.value = { message: (error as Error).message, steps: ["Check the cable and power, then try Reconnect again."] }; }
    finally { checking.value = false; }
  }
</script>
<template>
  <div class="space-y-2">
    <Button variant="outline" :disabled="checking || workshop.busy.value" @click="reconnect">{{ checking ? "Checking connection…" : device === "printer" ? "Reconnect printer" : "Reconnect webcam" }}</Button>
    <div v-if="result" role="status" class="space-y-1 text-sm">
      <p>{{ result.message }}</p>
      <ol class="list-decimal space-y-1 pl-5"><li v-for="step in result.steps" :key="step">{{ step }}</li></ol>
    </div>
  </div>
</template>
