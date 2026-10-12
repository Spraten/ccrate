<script setup lang="ts">
  import { DialogRoot } from "reka-ui";
  import { DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
  const props = defineProps<{ modelValue: boolean; title: string; description?: string; busy?: boolean }>();
  const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();
  function update(value: boolean) { if (!props.busy) emit("update:modelValue", value); }
</script>
<template>
  <DialogRoot :open="modelValue" @update:open="update">
    <DialogContent class="max-h-[90dvh] overflow-y-auto sm:max-w-xl" @escape-key-down="busy && $event.preventDefault()" @interact-outside="busy && $event.preventDefault()">
      <DialogHeader><DialogTitle>{{ title }}</DialogTitle><DialogDescription v-if="description">{{ description }}</DialogDescription></DialogHeader>
      <slot />
      <DialogFooter><slot name="actions" /></DialogFooter>
    </DialogContent>
  </DialogRoot>
</template>
