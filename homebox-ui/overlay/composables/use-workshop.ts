export type WorkshopContext = {
  user: { id: string; name: string; email: string };
  group: { id: string; name: string };
  manager: boolean;
  identity: string;
};
export type PendingAction = { key: string; path: string; label: string; subject: string; at: string; intent?: Record<string, unknown>; identity?: string; group_id?: string; user_id?: string };

export function workshopUUID() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 15) | 64;
  bytes[8] = (bytes[8]! & 63) | 128;
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function useWorkshop() {
  const context = useState<WorkshopContext | null>("workshop-context", () => null);
  const busy = useState<boolean>("workshop-writing", () => false);
  const { selectedId } = useCollections();
  const auth = useAuthContext();
  const group = () => selectedId.value || auth.user?.defaultGroupId;
  const manager = computed(() => !!context.value?.manager && context.value.user.id === auth.user?.id && context.value.group.id === group());

  async function request<T = any>(path: string, data?: Record<string, unknown>, identity?: string): Promise<T> {
    const currentGroup = group();
    const currentUser = auth.user?.id;
    const controller = new AbortController();
    const labelRead = ['labels/preview', 'labels/paper', 'labels/templates/result'].includes(path);
    const labelSave = path === 'labels/templates/save';
    const timer = setTimeout(() => controller.abort(), labelRead ? 60000 : 25000);
    try {
      const headers: Record<string, string> = {};
      if (currentGroup) headers["X-Workshop-Group"] = currentGroup;
      if (data !== undefined) { headers["Content-Type"] = "application/json"; headers["X-Workshop-Identity"] = identity || context.value?.identity || ""; }
      else if (path.startsWith("workshop/view") || ["workshop/checks/get", "workshop/checks/list"].includes(path.split("?")[0] ?? "")) headers["X-Workshop-Identity"] = context.value?.identity || "";
      const response = await fetch(`/workshop-api/${path}`, {
        method: data === undefined ? "GET" : "POST", credentials: "same-origin", headers,
        body: data === undefined ? undefined : JSON.stringify(data), signal: controller.signal,
      });
      const result = await response.json();
      if (currentGroup !== group() || currentUser !== auth.user?.id) throw new Error("Your account or collection changed. Reload before continuing.");
      if (!response.ok) {
        if (response.status === 401) { context.value = null; auth.invalidateSession(); void navigateTo("/"); }
        throw Object.assign(new Error(result.error || "The action could not be confirmed."), { status: response.status });
      }
      return result;
    } catch (error) {
      if ((error as Error).name === "AbortError") throw new Error(labelRead ? "Label preview timed out. Select fewer items or preview again." : labelSave ? "Template Save timed out. Its saved result can confirm the request." : "No confirmation received. Check Recovery before trying again.");
      throw error;
    } finally { clearTimeout(timer); }
  }

  async function refresh(): Promise<WorkshopContext> {
    const next = await request<WorkshopContext>("context");
    context.value = next;
    return next;
  }

  function pendingKey(ctx = context.value) { return ctx ? `workshop-pending:${ctx.group.id}:${ctx.user.id}` : ""; }
  function pending(): PendingAction[] {
    try { return JSON.parse(localStorage.getItem(pendingKey()) || "[]"); } catch { return []; }
  }
  function pendingTemplateSave(): PendingAction | null {
    const ctx = context.value;
    if (!ctx) return null;
    return pending().find(row => row.path === "labels/templates/save" && (
      row.identity === ctx.identity && row.group_id === ctx.group.id && row.user_id === ctx.user.id && row.intent?.request_key === row.key ||
      !row.identity && !row.group_id && !row.user_id && !row.intent && !!row.key
    )) || null;
  }
  function forget(key: string) { localStorage.setItem(pendingKey(), JSON.stringify(pending().filter(row => row.key !== key))); }
  function confirmTemplateSave(key: string) {
    const ctx = context.value;
    if (!ctx) return false;
    const rows = pending();
    if (!rows.some(row => row.key === key && row.path === "labels/templates/save" && (
      row.identity === ctx.identity && row.group_id === ctx.group.id && row.user_id === ctx.user.id && row.intent?.request_key === key ||
      !row.identity && !row.group_id && !row.user_id && !row.intent
    ))) return false;
    localStorage.setItem(pendingKey(), JSON.stringify(rows.filter(row => row.key !== key || row.path !== "labels/templates/save")));
    return true;
  }

  async function write<T = any>(path: string, data: Record<string, unknown>, label: string, subject = ""): Promise<T> {
    if (busy.value) throw new Error("Wait for the current confirmation to finish.");
    const expected = context.value;
    if (!expected) throw new Error("Reload the page before confirming.");
    busy.value = true;
    let sent = false;
    const key = String(data.request_key || workshopUUID());
    const intent = JSON.parse(JSON.stringify({ ...data, request_key: key })) as Record<string, unknown>;
    const storageKey = pendingKey(expected);
    try {
      const current = await refresh();
      if (current.identity !== expected.identity || !current.manager) throw new Error("Your account, collection or management access changed. Reload before confirming.");
      const badgePrint = (value: string) => ["badges/print", "badges/reprint"].includes(value);
      if (pending().some(row => row.subject === subject && (row.path === path || (badgePrint(row.path) && badgePrint(path))))) throw new Error("This action has an unconfirmed result. Check Recovery before trying again.");
      const pendingAction: PendingAction = { key, path, label, subject, at: new Date().toISOString() };
      if (path === "workshop/save" || path === "labels/templates/save") Object.assign(pendingAction, {
        intent, identity: expected.identity, group_id: expected.group.id, user_id: expected.user.id,
      });
      if (path.startsWith("workshop/checks/")) Object.assign(pendingAction, {
        identity: expected.identity, group_id: expected.group.id, user_id: expected.user.id,
      });
      localStorage.setItem(storageKey, JSON.stringify([...pending(), pendingAction]));
      sent = true;
      const result = await request<T>(path, intent, expected.identity);
      const rows: PendingAction[] = JSON.parse(localStorage.getItem(storageKey) || "[]");
      localStorage.setItem(storageKey, JSON.stringify(rows.filter(row => row.key !== key)));
      return result;
    } catch (error) {
      const status = (error as { status?: number }).status || 0;
      if (sent && path === "labels/templates/save" && [400, 409].includes(status)) confirmTemplateSave(key);
      if (sent && path !== "labels/templates/save" && [400, 409].includes(status)) {
        try {
          const result = await request<{ status: string }>("operation/status", { request_key: key }, expected.identity);
          if (["not_started", "cancelled"].includes(result.status)) forget(key);
        } catch { /* Preserve an uncertain request for recovery. */ }
      }
      throw error;
    } finally { busy.value = false; }
  }

  return { context, manager, busy, request, refresh, write, pending, pendingTemplateSave, forget, confirmTemplateSave };
}
