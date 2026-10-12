<script setup lang="ts">
  import BaseContainer from "@/components/Base/Container.vue";
  import { toast } from "@/components/ui/sonner";
  import { mountWorkshopTools } from "@/lib/workshop-tools.js";
  definePageMeta({ middleware: ["auth"], key: route => String(route.params.tool) });
  const route = useRoute(), router = useRouter();
  const workshop = useWorkshop();
  const { selectedId } = useCollections();
  const root = ref<HTMLElement | null>(null);
  const tool = computed(() => String(route.params.tool));
  const allowed = ["loans", "map", "imports", "labels", "recovery", "system"];
  const pageTitle = computed(() => tool.value === 'labels' ? 'Label maker' : tool.value === 'map' ? 'Workshop & storage' : tool.value.charAt(0).toUpperCase() + tool.value.slice(1));
  useHead({ title: computed(() => `C-Crate | ${pageTitle.value}`) });
  let mounted: ReturnType<typeof mountWorkshopTools> | null = null;
  const queryId = (value: unknown) => Array.isArray(value) ? String(value[0] || "") : String(value || "");
  async function mount() {
    mounted?.dispose(); mounted = null;
    if (!allowed.includes(tool.value)) { await navigateTo("/workshop/loans", { replace: true }); return; }
    const initialSelection: { entityId: string | null; drawingId: string | null; roomId: string | null } = { entityId: queryId(route.query.id) || null, drawingId: queryId(route.query.drawing_id) || null, roomId: queryId(route.query.room_id) || null };
    if (root.value) mounted = mountWorkshopTools(root.value, tool.value === "map" ? "workshop" : tool.value, workshop, (path: string, replace = false) => replace ? router.replace(path) : router.push(path), (text: string) => toast(text), initialSelection);
  }
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
  <BaseContainer>
    <div ref="root" class="workshop-native" @click="follow">
      <div id="view" tabindex="-1" class="space-y-4"><p class="text-sm text-muted-foreground">Loading workshop…</p></div>
      <dialog id="dialog" aria-labelledby="dialog-title"><div class="dialog-top"><h2 id="dialog-title"></h2><button id="dialog-close" type="button">Close</button></div><div id="dialog-body" class="dialog-body"></div></dialog>
    </div>
  </BaseContainer>
</template>
