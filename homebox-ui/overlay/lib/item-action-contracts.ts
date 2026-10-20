export type ItemActionKind = 'checkout' | 'checkin' | 'cart' | 'note';

export type ItemActionRequest =
  | { kind: Exclude<ItemActionKind, 'checkout'>; itemId: string; source: string }
  | { kind: 'checkout'; itemId: string; source: string }
  | { kind: 'checkout'; itemIds: string[]; cartRevision: number; source: 'cart' };

export type ItemActionResult = {
  kind: ItemActionKind;
  itemIds: string[];
  receiptId?: string;
  cartRevision?: number;
};
export type PendingItemAction = {
  path: string;
  request_key: string;
  kind: ItemActionKind;
  item_ids: string[];
  identity: string;
  group_id: string;
  user_id: string;
  payload: Record<string, unknown>;
};

export type ItemActionPhase = 'closed' | 'loading' | 'review' | 'verifying' | 'submitting' | 'uncertain' | 'success' | 'error';
export type ItemActionStatus = {
  id: string;
  availability: 'available' | 'checked_out' | 'blocked' | 'unknown';
  can_checkin?: boolean;
  can_add_note?: boolean;
  loan?: { borrower_id?: string; borrower_name?: string; operation_id?: string };
  borrower?: { id: string; name: string };
  borrower_id?: string;
  blocker?: string;
  location?: { id: string; name: string } | null;
};
export type ItemActionDraft = {
  notes?: Record<string, string>;
  note?: string;
  destination_id?: string;
  return_note?: string;
  problem?: string;
  verified?: string[];
  kit_versions?: Record<string, string>;
  kit_items?: Array<{ id: string; name: string; parent_id?: string }>;
};
export type ItemActionState = {
  phase: ItemActionPhase;
  request: ItemActionRequest | null;
  itemIds: string[];
  status: ItemActionStatus[];
  draft: ItemActionDraft;
  error: string;
  discardPrompt: boolean;
  verificationId: string | null;
  requiredItems: string[];
  verifiedItems: string[];
  kitVersions: Record<string, string>;
  requestKey: string | null;
  owner: string | null;
  dirty: boolean;
  receipt: Record<string, unknown> | null;
};
