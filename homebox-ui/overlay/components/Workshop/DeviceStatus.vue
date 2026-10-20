<script setup lang="ts">
  import { Camera, Printer, RefreshCw } from "lucide-vue-next";
  import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
  import { serializedDeviceRequest } from "@/composables/use-device-status";

  const props = defineProps<{ enabled?: boolean }>();
  type Device = { device: string; connected: boolean; reason?: string; message: string; steps: string[] };
  type State = Device & { checking?: boolean };
  const workshop = useWorkshop();
  const auth = useAuthContext();
  const trustNeedsConfirmation = useState<boolean>("workshop-device-status-trust-needs-confirmation", () => false);
  const trustGeneration = useState<number>("workshop-device-status-trust-generation", () => 0);
  const { selectedId } = useCollections();
  const lastChecked = ref(""), busy = ref(false), openDevice = ref<"printer" | "camera" | null>(null);
  const states = ref<Record<"printer" | "camera", State>>({
    printer: { device: "printer", connected: false, reason: "unknown", message: "Waiting for the first check.", steps: [] },
    camera: { device: "camera", connected: false, reason: "unknown", message: "Waiting for the first check.", steps: [] },
  });
  let timer: ReturnType<typeof setInterval> | null = null, disposed = false, confirming = false, revision = 0;
  const manager = computed(() => !trustNeedsConfirmation.value && workshop.manager.value);
  const active = computed(() => props.enabled !== false);
  const label = (device: "printer" | "camera") => device === "printer" ? "SUPVAN printer (Pi)" : "C920 camera (Pi)";
  const text = (state: State) => state.checking ? "Checking" : state.connected ? "Connected" : state.reason === "unknown" ? "Unavailable / Unknown" : state.reason === "disconnected" ? "Disconnected" : state.reason === "adapter_missing" ? "Software setup needed" : "Not ready";
  const color = (state: State) => state.checking || (!state.connected && state.reason !== "unknown" && state.reason !== "disconnected") ? "amber" : state.connected ? "green" : state.reason === "disconnected" ? "red" : "neutral";
  function unknown(message: string) {
    states.value = Object.fromEntries((['printer', 'camera'] as const).map(device => [device, {
      device, connected: false, reason: "unknown", message, steps: ["Check the Pi connection, then try Test connection again."],
    }])) as typeof states.value;
  }
  function clear() {
    revision++;
    openDevice.value = null;
    lastChecked.value = "";
    unknown("Device status is unavailable until a manager check completes.");
  }
  async function confirmContext() {
    if (confirming) return null;
    confirming = true;
    const generation = trustGeneration.value;
    try {
      const context = await workshop.refresh();
      if (!disposed && generation === trustGeneration.value) trustNeedsConfirmation.value = false;
      return context;
    } finally { confirming = false; }
  }
  async function handleProbeFailure(error: unknown, current: number) {
    if (disposed || current !== revision) return;
    const status = (error as { status?: number })?.status;
    unknown((error as Error).message || "The device check failed.");
    if (status === 403 || status === 409) {
      trustNeedsConfirmation.value = true;
      trustGeneration.value++;
      openDevice.value = null;
      workshop.context.value = null;
    }
    try { await confirmContext(); } catch { /* Trust stays cleared after an authorization or identity denial. */ }
  }
  async function refresh() {
    if (disposed || !active.value || busy.value || document.visibilityState !== "visible" || !manager.value) return;
    busy.value = true;
    const current = ++revision;
    states.value = Object.fromEntries((['printer', 'camera'] as const).map(device => [device, { ...states.value[device], checking: true }])) as typeof states.value;
    try {
      const result = await serializedDeviceRequest(
        () => workshop.request<{ printer: Device; camera: Device }>("hardware/status"),
        () => !disposed && current === revision && active.value && document.visibilityState === "visible" && !!manager.value,
      );
      if (!result) return;
      if (disposed || current !== revision || !manager.value) return;
      states.value = { printer: result.printer, camera: result.camera };
      lastChecked.value = new Date().toLocaleTimeString();
    } catch (error) {
      await handleProbeFailure(error, current);
    } finally {
      busy.value = false;
      if (!disposed && current !== revision && manager.value) queueMicrotask(visibleRefresh);
    }
  }
  async function action(device: "printer" | "camera", kind: "test" | "reconnect") {
    if (!active.value || busy.value || !manager.value || document.visibilityState !== "visible") return;
    busy.value = true;
    const current = ++revision;
    states.value[device] = { ...states.value[device], checking: true };
    try {
      const result = await serializedDeviceRequest(
        () => workshop.request<Device>("hardware/reconnect", { device }),
        () => !disposed && current === revision && active.value && document.visibilityState === "visible" && !!manager.value,
      );
      if (!result) return;
      if (disposed || current !== revision || !manager.value) return;
      states.value[device] = result;
      lastChecked.value = new Date().toLocaleTimeString();
      states.value[device].message = result.connected
        ? kind === "test" ? "Connection test passed." : "Reconnected and ready."
        : result.message;
    } catch (error) {
      await handleProbeFailure(error, current);
    } finally {
      busy.value = false;
      if (!disposed && current !== revision && manager.value) queueMicrotask(visibleRefresh);
    }
  }
  function visibleRefresh() {
    if (document.visibilityState !== "visible") return;
    if (trustNeedsConfirmation.value) void start();
    else void refresh();
  }
  watch([() => auth.user?.id, selectedId], () => { clear(); if (auth.user) void start(); }, { flush: "sync" });
  watch(() => workshop.context.value?.identity, (identity, previous) => { if (previous && identity !== previous) clear(); });
  watch(manager, value => { if (!value) clear(); else void refresh(); });
  watch(active, value => { if (value) void start(); else clear(); });
  async function start() {
    if (disposed || !active.value || confirming) return;
    const current = ++revision;
    try {
      await confirmContext();
      if (!disposed && active.value && current === revision && manager.value) await refresh();
    } catch { if (!disposed && current === revision) unknown("Manager permission or identity could not be confirmed."); }
  }
  onMounted(() => {
    if (active.value) void start();
    timer = setInterval(visibleRefresh, 30000);
    window.addEventListener("focus", visibleRefresh);
    document.addEventListener("visibilitychange", visibleRefresh);
  });
  onBeforeUnmount(() => {
    disposed = true; clear();
    if (timer) clearInterval(timer);
    window.removeEventListener("focus", visibleRefresh);
    document.removeEventListener("visibilitychange", visibleRefresh);
  });
</script>

<template>
  <div v-if="manager && active" class="device-status">
    <Popover v-for="device in (['printer', 'camera'] as const)" :key="device" :open="openDevice === device" @update:open="value => openDevice = value ? device : null">
      <PopoverTrigger as-child>
        <button type="button" class="device-status__trigger" :aria-label="`${label(device)}: ${text(states[device])}. Show device details`">
          <Printer v-if="device === 'printer'" aria-hidden="true" class="size-4" />
          <Camera v-else aria-hidden="true" class="size-4" />
          <span class="device-status__dot" :data-state="color(states[device])" aria-hidden="true" />
          <span class="device-status__name">{{ device === 'printer' ? 'Printer' : 'Camera' }}</span>
          <span class="device-status__state">{{ text(states[device]) }}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" class="device-status__panel w-[min(24rem,calc(100vw-1rem))] max-h-[75dvh] overflow-y-auto" :aria-label="`${label(device)} details`">
      <div class="device-status__row">
        <div class="device-status__heading">
          <Printer v-if="device === 'printer'" aria-hidden="true" class="size-4" />
          <Camera v-else aria-hidden="true" class="size-4" />
          <strong>{{ label(device) }}</strong><span>{{ text(states[device]) }}</span>
        </div>
        <p>{{ states[device].message }}</p>
        <ul v-if="states[device].steps.length"><li v-for="step in states[device].steps" :key="step">{{ step }}</li></ul>
        <div class="device-status__actions">
          <button type="button" :disabled="busy" @click="action(device, 'test')"><RefreshCw aria-hidden="true" class="size-3.5" />Test connection</button>
          <button type="button" :disabled="busy" @click="action(device, 'reconnect')">Reconnect</button>
        </div>
      </div>
      <p v-if="lastChecked" class="device-status__time">Last successful check: {{ lastChecked }}</p>
      </PopoverContent>
    </Popover>
  </div>
</template>

<style scoped>
  .device-status{display:flex;flex:none;align-items:center;gap:.25rem;white-space:nowrap}.device-status__trigger{position:relative;display:inline-flex;flex:none;min-height:2.25rem;align-items:center;gap:.35rem;white-space:nowrap;border:1px solid hsl(var(--border));border-radius:calc(var(--radius) - 2px);padding:.35rem .5rem;background:hsl(var(--background));color:hsl(var(--foreground));font-size:.75rem}.device-status__trigger:focus-visible,.device-status__actions button:focus-visible{outline:2px solid hsl(var(--ring));outline-offset:2px}.device-status__dot{width:.5rem;height:.5rem;flex:none;border-radius:50%;background:#737373}.device-status__dot[data-state=green]{background:#15803d}.device-status__dot[data-state=amber]{background:#b45309}.device-status__dot[data-state=red]{background:#b91c1c}.device-status__row{font-size:.8rem}.device-status__heading,.device-status__actions{display:flex;align-items:center;gap:.5rem}.device-status__heading span{margin-left:auto}.device-status__row p{margin:.4rem 0}.device-status__row ul{list-style:disc;padding-left:1.25rem}.device-status__actions{margin-top:.5rem}.device-status__actions button{display:inline-flex;min-height:2rem;align-items:center;gap:.35rem;border:1px solid hsl(var(--border));border-radius:calc(var(--radius) - 2px);padding:.25rem .5rem}.device-status__actions button:disabled{opacity:.5}.device-status__time{margin:.6rem 0 0;color:hsl(var(--muted-foreground));font-size:.75rem}@media(max-width:1024px){.device-status__state{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.device-status__trigger{padding:.35rem}}
  .device-status__dot[data-state=red]{background:#b91c1c}
</style>
