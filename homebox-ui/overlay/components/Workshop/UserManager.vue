<script setup lang="ts">
  import { Button } from "@/components/ui/button";
  import { Input } from "@/components/ui/input";
  import { Label } from "@/components/ui/label";
  import { Textarea } from "@/components/ui/textarea";
  import ActionDialog from "./ActionDialog.vue";
  import MemberAvatar from "./MemberAvatar.vue";
  import { prepareMemberAvatar } from "@/lib/member-avatar.js";
  import type { UserSummary } from "~~/lib/api/types/data-contracts";
  const props = defineProps<{ members: UserSummary[] }>();
  const emit = defineEmits<{ changed: [] }>();
  const workshop = useWorkshop(), auth = useAuthContext();
  const { selectedId } = useCollections();
  const open = ref(false), mode = ref<"list" | "new" | "edit">("list"), loading = ref(false), error = ref("");
  const search = ref("");
  type Profile = { id: string; name: string; email: string; avatar: string; notes: string; mode: string; updatedAt: string; editable: boolean; protected: boolean };
  const draft = ref<Profile | null>(null);
  let revision = 0;
  const visibleMembers = computed(() => props.members.filter(user => `${user.name} ${user.email} ${user.id}`.toLowerCase().includes(search.value.toLowerCase())));
  const busy = computed(() => workshop.busy.value || loading.value);
  function close() { if (busy.value) return; revision++; open.value = false; draft.value = null; error.value = ""; }
  function show(user?: UserSummary) { mode.value = "list"; search.value = ""; error.value = ""; open.value = true; if (user) void edit(user.id); }
  defineExpose({ show });
  function create() {
    revision++; mode.value = "new"; error.value = "";
    draft.value = { id: workshopUUID(), name: "", email: "", avatar: "", notes: "", mode: "badge-only", updatedAt: "", editable: true, protected: false };
  }
  async function edit(id: string) {
    const current = ++revision; loading.value = true; error.value = ""; draft.value = null; mode.value = "edit";
    try { const value = await workshop.request<Profile>(`users/profile?id=${encodeURIComponent(id)}`); if (current === revision) draft.value = value; }
    catch (cause) { if (current === revision) error.value = (cause as Error).message; }
    finally { if (current === revision) loading.value = false; }
  }
  async function picture(event: Event) {
    const input = event.target as HTMLInputElement, file = input.files?.[0], value = draft.value, current = revision;
    if (!file || !value) return;
    loading.value = true; error.value = "";
    try { const avatar = await prepareMemberAvatar(file); if (revision === current && draft.value === value) value.avatar = avatar; }
    catch (cause) { if (revision === current) error.value = (cause as Error).message; }
    finally { if (revision === current) loading.value = false; input.value = ""; }
  }
  async function save() {
    const value = draft.value; if (!value || busy.value) return;
    error.value = "";
    try {
      const result = mode.value === "new"
        ? await workshop.write<{ id: string }>("users/create", { name: value.name, email: value.email, request_key: value.id }, "Create user", value.id)
        : await workshop.write<{ id: string }>("users/update", { ...value, user_id: value.id }, "Save profile", value.id);
      emit("changed"); await edit(result.id);
    } catch (cause) { error.value = (cause as Error).message; }
  }
  watch([selectedId, () => auth.user?.id], () => { revision++; open.value = false; loading.value = false; draft.value = null; error.value = ""; });
  onBeforeUnmount(() => { revision++; draft.value = null; });
  onBeforeRouteLeave(() => { if (busy.value) return false; close(); });
</script>
<template>
  <ActionDialog :model-value="open" :busy="busy" :title="mode === 'new' ? 'Create user' : mode === 'edit' ? 'Manage profile' : 'Manage users'" description="People, profile pictures and optional details for this collection." @update:model-value="!$event && close()">
    <template v-if="mode === 'list'">
      <Label for="member-search">Find a user</Label><Input id="member-search" v-model="search" placeholder="Name, email or user ID" />
      <div class="max-h-72 space-y-2 overflow-auto">
        <Button v-for="user in visibleMembers" :key="user.id" variant="outline" class="h-auto w-full justify-start gap-3 py-3" @click="edit(user.id)">
          <MemberAvatar :member-id="user.id" :name="user.name" :picture="user.avatar" />
          <span class="min-w-0 text-left"><span class="block font-medium">{{ user.name }}</span><span class="block text-xs text-muted-foreground">{{ user.email || 'Email not provided' }} · ID {{ user.id.slice(0,8) }}</span></span>
        </Button>
        <p v-if="!visibleMembers.length" class="text-sm text-muted-foreground">No matching users.</p>
      </div>
    </template>
    <p v-if="loading" role="status" class="text-sm">Loading profile…</p>
    <template v-if="draft">
      <div class="flex items-center gap-3"><MemberAvatar :member-id="draft.id" :name="draft.name || 'New user'" :picture="draft.avatar" /><span class="text-sm">{{ draft.mode === 'badge-only' ? 'Badge-only person' : 'Existing web account' }}</span></div>
      <p v-if="!draft.editable" class="text-sm text-muted-foreground">This profile is managed in the person's primary collection.</p>
      <Label for="member-name">Name</Label><Input id="member-name" v-model="draft.name" :disabled="busy || !draft.editable" maxlength="255" autocomplete="off" />
      <Label for="member-email">{{ draft.mode === 'badge-only' ? 'Email (optional)' : 'Sign-in email' }}</Label><Input id="member-email" v-model="draft.email" type="email" :disabled="busy || !draft.editable || (draft.protected && draft.mode !== 'badge-only')" maxlength="255" autocomplete="off" />
      <p v-if="draft.protected" class="text-xs text-muted-foreground">The collection owner's sign-in details are protected here.</p>
      <p v-if="mode === 'new'" class="text-sm text-muted-foreground">Only a name is needed. A generated picture is ready; you can change it after creation. Issue or print a badge from the member's Kiosk Badge actions.</p>
      <template v-else>
        <Label for="member-picture">Profile picture</Label><Input id="member-picture" type="file" accept="image/png,image/jpeg,image/webp" :disabled="busy || !draft.editable" @change="picture" />
        <Button variant="outline" size="sm" :disabled="busy || !draft.editable || !draft.avatar" @click="draft.avatar = ''">Use generated picture</Button>
        <Label for="member-notes">Other details (optional)</Label><Textarea id="member-notes" v-model="draft.notes" :disabled="busy || !draft.editable" maxlength="1000" />
        <p class="break-all text-xs text-muted-foreground">User ID: {{ draft.id }}</p>
      </template>
    </template>
    <p v-if="error" role="alert" class="text-sm text-destructive">{{ error }}</p>
    <template #actions>
      <Button variant="outline" :disabled="busy" @click="close">Close</Button>
      <Button v-if="mode !== 'list'" variant="outline" :disabled="busy" @click="mode = 'list'; draft = null; error = ''">Back to users</Button>
      <Button v-if="mode === 'list'" :disabled="busy" @click="create">New user</Button>
      <Button v-else-if="draft?.editable" :disabled="busy || !draft.name.trim()" @click="save">{{ mode === 'new' ? 'Create user' : 'Save profile' }}</Button>
    </template>
  </ActionDialog>
</template>
