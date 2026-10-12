<script setup lang="ts">
  import { memberAvatar } from "@/lib/member-avatar.js";
  defineProps<{ memberId: string; name: string; picture?: string }>();
</script>
<template>
  <img :src="picture || memberAvatar(memberId)" :alt="(picture ? 'Profile picture for ' : 'Generated avatar for ') + name" width="40" height="40" class="size-10 shrink-0 rounded-md border bg-muted" />
</template>
