<script setup lang="ts">
  import DeviceReconnect from "./DeviceReconnect.vue";
  import { Button } from "@/components/ui/button";
  import { Badge } from "@/components/ui/badge";
  import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
  import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
  import { toast } from "@/components/ui/sonner";
  import { Printer, QrCode, ShieldCheck } from "lucide-vue-next";
  import ActionDialog from "./ActionDialog.vue";
  type MemberBadge = { id: string; revoked: boolean; created_at?: string; reprintable?: boolean };
  const props = defineProps<{ member: { id: string; name: string; email?: string }; badges: MemberBadge[]; canManage: boolean; protectedOwner?: boolean }>();
  const emit = defineEmits<{ changed: [] }>();
  const workshop = useWorkshop();
  const { busy, manager } = workshop;
  const mode = ref<"manage" | "issue" | "revoke" | "permission" | "issued" | "reprint" | null>(null);
  const target = ref("");
  const issued = ref<{ id: string; code?: string; qr?: string } | null>(null);
  const error = ref("");
  const printed = ref(false);
  const active = computed(() => props.badges.filter(badge => !badge.revoked));
  const selected = computed(() => active.value.find(badge => badge.id === target.value));
  const title = computed(() => mode.value === "manage" ? "Manage badges" : mode.value === "reprint" ? "Reprint badge" : mode.value === "permission" ? `${props.canManage ? "Remove" : "Allow"} management access` : mode.value === "revoke" ? "Revoke badge" : mode.value === "issued" ? `Badge for ${props.member.name}` : "Issue personal badge");
  function date(value?: string) { return value ? new Date(value).toLocaleString() : "Earlier badge"; }
  function open(action: "manage" | "issue" | "revoke" | "permission" | "reprint", id?: string) { mode.value = action; target.value = id || active.value[0]?.id || ""; issued.value = null; error.value = ""; printed.value = false; }
  function close() { if (busy.value) return; mode.value = null; issued.value = null; error.value = ""; }
  watch(() => workshop.context.value?.identity, () => { mode.value = null; issued.value = null; error.value = ""; });
  onBeforeUnmount(() => { issued.value = null; mode.value = null; });
  onBeforeRouteLeave(() => { if (busy.value) return false; close(); });
  async function confirm() {
    error.value = "";
    try {
      if (mode.value === "issue") {
        issued.value = await workshop.write("badges/issue", { user_id: props.member.id }, "Issue badge", props.member.id);
        mode.value = "issued"; emit("changed");
      } else if (mode.value === "reprint") {
        if (!selected.value) throw new Error("Choose an active badge.");
        if (!selected.value.reprintable) {
          issued.value = await workshop.write("badges/replace", { badge_id: target.value }, "Replace older badge", target.value);
          mode.value = "issued"; emit("changed");
        } else {
          await workshop.write("badges/reprint", { badge_id: target.value }, "Reprint badge", target.value);
          printed.value = true; toast.success("Badge reprinted. Inspect the physical label.");
        }
      } else if (mode.value === "revoke") {
        await workshop.write("badges/revoke", { id: target.value }, "Revoke badge", target.value); close(); emit("changed"); toast.success("Badge revoked.");
      } else {
        await workshop.write("permissions/set", { user_id: props.member.id, enabled: !props.canManage }, "Update management access", props.member.id); close(); emit("changed"); toast.success("Management access updated.");
      }
    } catch (cause) { error.value = (cause as Error).message; }
  }
  async function print() {
    if (!issued.value?.code || printed.value) return;
    error.value = "";
    try {
      await workshop.write("badges/print", { badge_id: issued.value.id, code: issued.value.code }, "Print badge", issued.value.id);
      printed.value = true; toast.success("Badge printed. Inspect the physical label.");
    } catch (cause) { error.value = (cause as Error).message; }
  }
</script>
<template>
  <div v-if="manager" class="space-y-2">
    <Badge variant="outline">{{ active.length }} active {{ active.length === 1 ? "badge" : "badges" }}</Badge>
    <div class="flex flex-wrap gap-2">
      <Button variant="outline" size="sm" :disabled="busy || !active.length" @click="open('reprint')"><Printer class="mr-2 size-4" />Reprint badge</Button>
      <Button variant="outline" size="sm" :disabled="busy" @click="open('manage')"><QrCode class="mr-2 size-4" />Manage badges</Button>
    </div>
    <ActionDialog :model-value="mode !== null" :title="title" :busy="busy" :description="member.name + (member.email ? ' · ' + member.email : '')" @update:model-value="!$event && close()">
      <template v-if="mode === 'manage'">
        <p v-if="!badges.length" class="text-sm text-muted-foreground">No badges have been issued for this member.</p>
        <Table v-else>
          <TableHeader><TableRow><TableHead>Issued</TableHead><TableHead>Status</TableHead><TableHead></TableHead></TableRow></TableHeader>
          <TableBody><TableRow v-for="badge in badges" :key="badge.id">
            <TableCell>{{ date(badge.created_at) }}</TableCell>
            <TableCell><Badge variant="outline">{{ badge.revoked ? 'Revoked' : 'Active' }}</Badge></TableCell>
            <TableCell><Button v-if="!badge.revoked" variant="outline" size="sm" :disabled="busy" @click="open('revoke', badge.id)">Revoke badge</Button></TableCell>
          </TableRow></TableBody>
        </Table>
        <Button v-if="member.id !== workshop.context.value?.user.id && !protectedOwner" variant="ghost" size="sm" :disabled="busy" @click="open('permission')"><ShieldCheck class="mr-2 size-4" />{{ canManage ? "Remove management access" : "Allow management" }}</Button>
      </template>
      <template v-else-if="mode === 'reprint'">
        <Select v-if="active.length > 1" v-model="target" :disabled="busy || printed">
          <SelectTrigger aria-label="Badge to reprint"><SelectValue placeholder="Choose badge" /></SelectTrigger>
          <SelectContent><SelectItem v-for="badge in active" :key="badge.id" :value="badge.id">Issued {{ date(badge.created_at) }}</SelectItem></SelectContent>
        </Select>
        <p v-if="selected?.reprintable" class="text-sm">Print one more copy of this member's existing badge. Both copies identify the same person.</p>
        <p v-else class="text-sm">The original QR was not saved for this older badge. Create a replacement first, then print it. Replacing it disables the old badge and ends its active kiosk sessions. Future copies can be reprinted.</p>
        <p v-if="printed" role="status" class="text-sm">Reprinted on the workshop printer. Inspect the badge.</p>
      </template>
      <template v-else-if="mode === 'issued'">
        <img v-if="issued?.qr" :src="issued.qr" :alt="'Personal badge for ' + member.name" class="mx-auto size-56 rounded-md bg-white p-2" />
        <p class="text-sm text-muted-foreground">Keep this badge with its owner. You can reprint it later from Members.</p>
        <p v-if="printed" role="status" class="text-sm">Printed on the workshop printer. Inspect the badge.</p>
      </template>
      <p v-else class="text-sm">{{ mode === 'issue' ? 'Create a new kiosk badge for this C-Crate member. Printing is a separate confirmation.' : mode === 'revoke' ? 'This badge will stop identifying its owner and end its active kiosk sessions.' : canManage ? 'Their C-Crate account and kiosk badges remain available.' : 'They can manage badges, labels, imports, workshop storage and recovery with their own C-Crate account.' }}</p>
      <DeviceReconnect v-if="mode === 'issued' || mode === 'reprint'" device="printer" />
      <p v-if="error" role="alert" class="rounded-md border border-destructive p-3 text-sm">{{ error }} <NuxtLink to="/workshop/recovery" class="underline">Open recovery</NuxtLink></p>
      <template #actions>
        <Button variant="outline" :disabled="busy" @click="close">{{ mode === 'issued' || mode === 'manage' || printed ? "Done" : "Cancel" }}</Button>
        <Button v-if="mode === 'manage'" :disabled="busy" @click="open('issue')">Issue badge</Button>
        <Button v-else-if="mode === 'issued' && issued?.code" :disabled="busy || printed" @click="print"><Printer class="mr-2 size-4" />{{ printed ? "Printed" : "Print one badge" }}</Button>
        <Button v-else-if="mode !== 'issued'" :disabled="busy || printed" @click="confirm">{{ mode === 'issue' ? "Confirm badge issuance" : mode === 'revoke' ? "Confirm revocation" : mode === 'reprint' ? selected?.reprintable ? "Confirm reprint" : "Confirm replacement" : "Confirm management access" }}</Button>
      </template>
    </ActionDialog>
  </div>
</template>
