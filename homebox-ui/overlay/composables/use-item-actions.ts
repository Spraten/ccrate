import { createItemActionController, createItemActionState } from "@/lib/item-actions.js";
import { useWorkshop, workshopUUID } from "@/composables/use-workshop";
import type { ItemActionRequest, ItemActionResult, ItemActionState, ItemActionStatus, PendingItemAction } from "@/lib/item-action-contracts";
import { normalizeItemActionStatus } from "@/lib/item-actions.js";

type SharedActionStore = {
  state: ItemActionState;
  changed: ReturnType<typeof shallowRef<ItemActionResult | null>>;
  pendingRevision: ReturnType<typeof shallowRef<number>>;
  controller: ReturnType<typeof createItemActionController>;
  loadStatus: (itemId: string, refresh?: boolean) => Promise<ItemActionStatus>;
  invalidateStatus: (itemIds: string[]) => void;
};
const stores = new WeakMap<object, SharedActionStore>();

export function useItemActions() {
  const app = useNuxtApp();
  let shared = stores.get(app);
  if (!shared) {
    const workshop = useWorkshop();
    const { selectedId } = useCollections();
    const auth = useAuthContext();
    const state = reactive(createItemActionState()) as ItemActionState;
    const changed = shallowRef<ItemActionResult | null>(null);
    const pendingRevision = shallowRef(0);
    const statusCache = new Map<string, Map<string, ItemActionStatus>>();
    const statusVersions = new Map<string, Map<string, number>>();
    const statusQueues = new Map<string, Map<string, { version: number; waiters: Array<{ resolve: (row: ItemActionStatus) => void; reject: (error: Error) => void }> }>>();
    let statusInFlight = 0, statusFlushQueued = false;
    const binding = () => {
      const context = workshop.context.value;
      return `${selectedId.value || auth.user?.defaultGroupId || ""}:${context?.user.id || auth.user?.id || ""}:${context?.group.id || ""}:${context?.identity || ""}`;
    };
    const invalidatedError = () => new Error("The selected account or collection changed while status was loading.");
    const invalidateStatus = (itemIds: string[]) => {
      for (const [scope, cache] of statusCache) for (const id of itemIds) cache.delete(id);
      for (const scope of statusVersions.keys()) {
        let versions = statusVersions.get(scope)!;
        for (const id of itemIds) versions.set(id, (versions.get(id) || 0) + 1);
      }
    };
    const pumpStatuses = () => {
      statusFlushQueued = false;
      while (statusInFlight < 4) {
        const currentBinding = binding();
        const queue = statusQueues.get(currentBinding);
        if (!queue?.size) return;
        const batch = [...queue.entries()].slice(0, 50);
        for (const [id] of batch) queue.delete(id);
        if (!queue.size) statusQueues.delete(currentBinding);
        const ids = batch.map(([id]) => id), capturedVersions = new Map(batch.map(([id, job]) => [id, job.version]));
        const identity = workshop.context.value?.identity;
        statusInFlight++;
        void workshop.request<ItemActionStatus[] | { items: ItemActionStatus[] }>(`item-actions/status?ids=${encodeURIComponent(ids.join(","))}`, undefined, identity)
          .then(raw => {
            if (binding() !== currentBinding || workshop.context.value?.identity !== identity) throw invalidatedError();
            const rows = normalizeItemActionStatus(raw);
            if (rows.length !== ids.length || rows.some((row, index) => row.id !== ids[index])) throw new Error("Equipment action status response did not match the requested units.");
            const cache = statusCache.get(currentBinding) || new Map<string, ItemActionStatus>();
            statusCache.set(currentBinding, cache);
            for (const row of rows) {
              const version = statusVersions.get(currentBinding)?.get(row.id) || 0;
              if (version !== capturedVersions.get(row.id)) throw invalidatedError();
              cache.set(row.id, row);
              for (const waiter of batch.find(([id]) => id === row.id)![1].waiters) waiter.resolve(row);
            }
          })
          .catch(error => {
            for (const [, job] of batch) for (const waiter of job.waiters) waiter.reject(error instanceof Error ? error : new Error(String(error)));
          })
          .finally(() => {
            statusInFlight--;
            if ([...statusQueues.values()].some(queue => queue.size)) scheduleStatusPump();
          });
      }
    };
    const scheduleStatusPump = () => {
      if (statusFlushQueued) return;
      statusFlushQueued = true;
      queueMicrotask(pumpStatuses);
    };
    const loadStatus = (itemId: string, refresh = false) => {
      const scope = binding();
      if (refresh) statusCache.get(scope)?.delete(itemId);
      const cached = statusCache.get(scope)?.get(itemId);
      if (cached) return Promise.resolve(cached);
      let versions = statusVersions.get(scope);
      if (!versions) statusVersions.set(scope, versions = new Map());
      let queue = statusQueues.get(scope);
      if (!queue) statusQueues.set(scope, queue = new Map());
      const version = versions.get(itemId) || 0;
      return new Promise<ItemActionStatus>((resolve, reject) => {
        const existing = queue!.get(itemId);
        if (existing && existing.version === version) existing.waiters.push({ resolve, reject });
        else queue!.set(itemId, { version, waiters: [{ resolve, reject }] });
        scheduleStatusPump();
      });
    };
    const controller = createItemActionController({
      request: (path: string, body?: Record<string, unknown>, identity?: string) => workshop.request(path, body, identity),
      getContext: () => workshop.context.value,
      uuid: workshopUUID,
      state,
      onChanged: ((value: ItemActionResult) => {
        if (value.kind !== "cart") invalidateStatus(value.itemIds);
        changed.value = {
          kind: value.kind,
          itemIds: value.itemIds,
          ...(value.receiptId ? { receiptId: value.receiptId } : {}),
          ...(value.cartRevision !== undefined ? { cartRevision: value.cartRevision } : {}),
        };
      }) as unknown as () => void,
    });
    controller.setStateListener(() => { pendingRevision.value++; });
    let previousBinding = binding();
    watch(binding, next => {
      if (next !== previousBinding) {
        changed.value = null;
        statusCache.clear(); statusVersions.clear();
        for (const queue of statusQueues.values()) for (const job of queue.values()) for (const waiter of job.waiters) waiter.reject(invalidatedError());
        statusQueues.clear();
        controller.resetContext();
      }
      previousBinding = next;
      controller.syncContext();
    });
    shared = { state, changed, pendingRevision, controller, loadStatus, invalidateStatus };
    stores.set(app, shared);
  }
  const { state, changed, pendingRevision, controller, loadStatus, invalidateStatus } = shared;
  return {
    state,
    changed,
    pendingRevision,
    loadStatus,
    invalidateStatus,
    open: (request: ItemActionRequest, trigger?: HTMLElement | null) => controller.open(request, trigger as never),
    close: () => controller.close(),
    discard: () => controller.discard(),
    setNote: (itemId: string, value: string) => controller.setNote(itemId, value),
    setDraft: (draft: Record<string, unknown>) => controller.setDraft(draft),
    changeSelection: (ids: string[], revision: number) => controller.changeSelection(ids, revision),
    verifyBadge: (code: string) => controller.verifyBadge(code),
    verifyItem: (code: string) => controller.verifyItem(code),
    verifyReturnItem: (code: string) => controller.verifyReturnItem(code),
    confirm: () => controller.confirm(),
    reconcile: () => controller.reconcile(),
    pending: () => controller.pendingActions() as PendingItemAction[],
    pendingError: () => controller.pendingError(),
    recoverPending: (row: PendingItemAction) => controller.recoverPending(row),
  };
}
