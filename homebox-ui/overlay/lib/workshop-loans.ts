export type WorkshopLoan = {
  entity_id: string;
  actor_id: string;
  entity_name: string;
  assetId?: string;
  borrower: string;
  unavailable?: boolean;
  checked_out_at?: string;
  imageId?: string | null;
  thumbnailId?: string | null;
};

export type WorkshopHistoryRow = {
  id: string;
  source: string;
  action: string;
  status: string;
  actor_id: string;
  actor: string;
  created_at: string;
  confirmed_at?: string | null;
  time_basis?: "request" | "confirmation";
  assets: string[];
  note_text?: string;
  note_state?: string;
  note_author?: string;
  return_notes?: Array<{ text: string; author?: string; created_at?: string }>;
  checkout_notes?: Array<{ entity_id: string; text: string; author: string; created_at: string }>;
  previous_borrowers?: Array<{ user_id?: string; name?: string; name_snapshot?: string }>;
};
