<script setup lang="ts">
import { mountLabelDesigner } from "../../lib/label-editor.js";
const props = defineProps<{ selectedItem?: string }>();
const emit = defineEmits<{ dirty: [value: boolean]; busy: [value: boolean] }>();
const workshop = useWorkshop();
const { selectedId } = useCollections();
const frameRoot = ref<HTMLElement | null>(null);
let frame: ReturnType<typeof mountLabelDesigner> | null = null;
const source = "/workshop-api/label-assets/editor.html";
async function request(action: string, data?: any) {
  if (action === "labels/templates") return workshop.request("labels/templates");
  return workshop.request(action, data);
}
watch([selectedId, () => workshop.context.value?.identity], () => { if (!frame) return; frame.dispose(); frame = null; emit('dirty', false); emit('busy', false); });
onMounted(() => {
  if (!frameRoot.value) return;
  frame = mountLabelDesigner(frameRoot.value, { src: source, context: () => workshop.context.value, request, write: () => { throw Error("Use the reviewed item action to confirm physical printing."); }, dirty: (v: boolean) => emit("dirty", v), busy: (v: boolean) => emit("busy", v) });
});
onBeforeUnmount(() => frame?.dispose());
defineExpose({ canLeave: () => frame?.canLeave() ?? true });
</script>
<template><div ref="frameRoot" class="label-designer-frame min-w-0 overflow-auto rounded-md border bg-white" /></template>
<style scoped>
.label-designer-frame { min-height: 580px; }
</style>
