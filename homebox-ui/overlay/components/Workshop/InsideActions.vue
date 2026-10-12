<script setup lang="ts">
  import { Button } from "@/components/ui/button";
  import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
  import { useDialog } from "@/components/ui/dialog-provider";
  import { DialogID } from "@/components/ui/dialog-provider/utils";
  const props = defineProps<{ entityId: string; archived?: boolean }>();
  const { openDialog } = useDialog();
  function create(baseType: "item" | "location") {
    openDialog(DialogID.CreateEntity, { params: { baseType, parentId: props.entityId } });
  }
</script>
<template>
  <DropdownMenu>
    <Button as-child variant="outline"><NuxtLink :to="`/workshop/map?id=${encodeURIComponent(entityId)}`">Show on map</NuxtLink></Button>
    <DropdownMenuTrigger as-child><Button variant="outline" :disabled="archived">Add inside</Button></DropdownMenuTrigger>
    <DropdownMenuContent align="end">
      <DropdownMenuItem @select="create('item')">Item inside</DropdownMenuItem>
      <DropdownMenuItem @select="create('location')">Location inside</DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
