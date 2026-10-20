<script setup lang="ts">
  import BaseContainer from "@/components/Base/Container.vue";
  import { toast } from "@/components/ui/sonner";
  import { mountWorkshopTools } from "@/lib/workshop-tools.js";
  import { useItemActions } from "@/composables/use-item-actions";
  import LabelGenerator from "@/components/Workshop/LabelGenerator.vue";
  definePageMeta({ middleware: ["auth"], key: route => String(route.params.tool) });
  const route = useRoute(), router = useRouter();
  const workshop = useWorkshop();
  const itemActions = useItemActions();
  const { selectedId } = useCollections();
  const root = ref<HTMLElement | null>(null);
  const labelWorkspace = shallowRef<any>(null);
  const labelStatus = ref("Loading equipment and saved designs…");
  const tool = computed(() => String(route.params.tool));
  const allowed = ["loans", "map", "equipment", "checkout-cart", "imports", "labels", "recovery", "system", "equipment-ids"];
  const pageTitle = computed(() => tool.value === 'labels' ? 'Label maker' : tool.value === 'map' ? 'Workshop & storage' : tool.value === 'checkout-cart' ? 'Checkout cart' : tool.value === 'equipment-ids' ? 'Equipment ID codes' : tool.value.charAt(0).toUpperCase() + tool.value.slice(1));
  useHead({ title: computed(() => `C-Crate | ${pageTitle.value}`) });
  let mounted: ReturnType<typeof mountWorkshopTools> | null = null;
  const queryId = (value: unknown) => Array.isArray(value) ? String(value[0] || "") : String(value || "");
  async function mount() {
    mounted?.dispose(); mounted = null;
    labelWorkspace.value = null;
    labelStatus.value = "Loading equipment and saved designs…";
    if (!allowed.includes(tool.value)) { await navigateTo("/workshop/loans", { replace: true }); return; }
    const initialSelection: { entityId: string | null; drawingId: string | null; roomId: string | null } = { entityId: queryId(route.query.id) || null, drawingId: queryId(route.query.drawing_id) || null, roomId: queryId(route.query.room_id) || null };
    if (root.value) mounted = mountWorkshopTools(root.value, tool.value === "map" ? "workshop" : tool.value, workshop, (path: string, replace = false) => replace ? router.replace(path) : router.push(path), (text: string) => toast(text), initialSelection, (workspace: any, status?: string) => { if (!workspace) { labelWorkspace.value = null; labelStatus.value = status || "Your C-Crate access changed. Open C-Crate again and check your account and collection."; return null; } const state = reactive(workspace); labelWorkspace.value = state; labelStatus.value = ""; return state; }, (request: any, trigger?: HTMLElement) => itemActions.open(request, trigger));
  }
  watch(itemActions.changed, result => { if (result) void mounted?.refreshItemAction(result); });
  function follow(event: MouseEvent) {
    const anchor = (event.target as HTMLElement).closest("a");
    if (anchor && anchor.origin === location.origin && !event.ctrlKey && !event.metaKey && !event.shiftKey && !anchor.target) { event.preventDefault(); void router.push(anchor.pathname + anchor.search); }
  }
  watch(selectedId, mount);
  watch(() => [queryId(route.query.id), queryId(route.query.drawing_id), queryId(route.query.room_id)], ([id, drawingId, roomId]) => {
    if (tool.value === "map" && mounted) void mounted.updateWorkshopSelection({ entityId: id || null, drawingId: drawingId || null, roomId: roomId || null });
  });
  onMounted(mount);
  onBeforeRouteLeave(() => mounted?.canLeave() ?? true);
  onBeforeUnmount(() => { mounted?.dispose(); });
</script>
<template>
  <BaseContainer :class="tool === 'labels' || tool === 'map' ? 'max-w-none px-3 sm:px-4 lg:px-5' : undefined">
    <LabelGenerator v-if="tool === 'labels'" :key="String(selectedId || '')" :workspace="labelWorkspace" :status="labelStatus" />
    <div ref="root" class="workshop-native" @click="follow">
      <div id="view" tabindex="-1" class="space-y-4" :class="{ hidden: tool === 'labels' }"><p class="text-sm text-muted-foreground">Loading workshop…</p></div>
      <dialog id="dialog" aria-labelledby="dialog-title"><div class="dialog-top"><h2 id="dialog-title"></h2><button id="dialog-close" type="button">Close</button></div><div id="dialog-body" class="dialog-body"></div></dialog>
    </div>
  </BaseContainer>
</template>
