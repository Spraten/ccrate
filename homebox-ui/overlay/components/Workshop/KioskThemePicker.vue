<script setup lang="ts">
import { Button } from "@/components/ui/button";
import { useTheme } from "@/composables/use-theme";
import { themes } from "~~/lib/data/themes";
import type { DaisyTheme } from "~~/lib/data/themes";

const workshop = useWorkshop();
const { theme } = useTheme();
const savedTheme = ref<DaisyTheme | "">("");
const busy = ref(false);
const message = ref("");
const error = ref("");
const canManage = computed(() => workshop.manager.value);
const themeLabel = (value: string) => themes.find(entry => entry.value === value)?.label || value;

async function load() {
  error.value = "";
  try {
    const current = await workshop.refresh();
    if (!current.manager) return;
    const result = await workshop.request<{ theme: DaisyTheme }>("kiosk/theme");
    savedTheme.value = result.theme;
  } catch (cause) { error.value = (cause as Error).message; }
}
async function applyCurrentTheme() {
  if (busy.value || !canManage.value) return;
  busy.value = true; message.value = ""; error.value = "";
  try {
    const current = await workshop.refresh();
    if (!current.manager) throw new Error("Manager access is required to change the touchscreen theme.");
    const result = await workshop.request<{ theme: DaisyTheme }>("kiosk/theme", { theme: theme.value });
    savedTheme.value = result.theme;
    message.value = `Touchscreen theme set to ${themeLabel(result.theme)}.`;
  } catch (cause) { error.value = (cause as Error).message; }
  finally { busy.value = false; }
}

onMounted(load);
</script>

<template>
  <section v-if="canManage" class="mt-5 border-t pt-4" aria-labelledby="kiosk-theme-heading">
    <h3 id="kiosk-theme-heading" class="text-sm font-semibold">Touchscreen theme</h3>
    <p class="mt-1 text-sm text-muted-foreground">Use the selected Homebox theme on the shared check-in and checkout screen.</p>
    <div class="mt-3 flex flex-wrap items-center gap-3">
      <Button type="button" size="sm" variant="outline" :disabled="busy || savedTheme === theme" @click="applyCurrentTheme">
        {{ busy ? 'Saving…' : savedTheme === theme ? 'Using this theme' : 'Use current theme on touchscreen' }}
      </Button>
      <span v-if="savedTheme" class="text-sm text-muted-foreground">Current: {{ themeLabel(savedTheme) }}</span>
      <span v-if="message" class="text-sm text-success" role="status">{{ message }}</span>
      <span v-if="error" class="text-sm text-destructive" role="alert">{{ error }} <button class="underline" type="button" @click="load">Retry</button></span>
    </div>
  </section>
</template>
