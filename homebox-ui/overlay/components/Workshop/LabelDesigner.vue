<script setup lang="ts">
import { mountLabelDesigner } from "../../lib/label-editor.js";
type SelectedItem = { id: string; name: string; assetId?: string };
const props = defineProps<{ selectedItem?: SelectedItem }>();
const emit = defineEmits<{ dirty: [value: boolean]; busy: [value: boolean]; ready: [handle: ReturnType<typeof mountLabelDesigner>]; closed: [] }>();
const workshop = useWorkshop();
const { selectedId } = useCollections();
const frameRoot = ref<HTMLElement | null>(null);
let frame: ReturnType<typeof mountLabelDesigner> | null = null;
const source = "/workshop-api/label-assets/editor.html";
function editorContext() {
  const css = getComputedStyle(document.documentElement);
  const token = (name: string, fallback: string) => `hsl(${css.getPropertyValue(name).trim() || fallback})`;
  return {
    ...workshop.context.value,
    selected_item: props.selectedItem ? { entity_id: props.selectedItem.id, name: props.selectedItem.name, asset_code: props.selectedItem.assetId || "" } : null,
    theme: {
      background: token("--background", "0 0% 100%"), foreground: token("--foreground", "222 47% 11%"),
      muted: token("--muted", "210 40% 96%"), mutedForeground: token("--muted-foreground", "215 16% 47%"),
      border: token("--border", "214 32% 91%"), primary: token("--primary", "142 38% 35%"), accent: token("--accent", "142 30% 94%"),
    },
  };
}
async function request(action: string, data?: any) {
  if (action === "labels/templates") return workshop.request("labels/templates");
  return workshop.request(action, data);
}
watch([selectedId, () => workshop.context.value?.identity], () => { if (!frame) return; frame.dispose(); frame = null; emit('dirty', false); emit('busy', false); });
onMounted(() => {
  if (!frameRoot.value) return;
  frame = mountLabelDesigner(frameRoot.value, { src: source, context: editorContext, request, write: (action: string, data: any, label: string, subject: string) => { if (action !== "labels/templates/save") throw Error("Use the reviewed item action to confirm physical printing."); return workshop.write(action, data, label, subject); }, dirty: (v: boolean) => emit("dirty", v), busy: (v: boolean) => emit("busy", v) });
  emit("ready", frame);
});
watch(() => props.selectedItem, () => { if (frame) frame.updateContext?.(editorContext()); }, { deep: true });
onBeforeUnmount(() => { frame?.dispose(); emit("closed"); });
defineExpose({ canLeave: () => frame?.canLeave() ?? true, dispose: () => frame?.dispose() });
</script>
<template><div ref="frameRoot" class="label-designer-frame min-w-0 overflow-auto rounded-md border bg-white" /></template>
<style scoped>
.label-designer-frame { min-height: 580px; }
</style>
