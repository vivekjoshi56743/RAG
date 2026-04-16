export type DocumentStatus = "uploaded" | "processing" | "indexed" | "error";
export type AccessRole = "viewer" | "editor" | "admin" | "owner";

export interface User {
  id: string;
  email: string;
  display_name?: string | null;
}

export interface Document {
  id: string;
  user_id: string;
  name: string;
  file_path: string;
  signed_url?: string | null;
  file_size?: number | null;
  mime_type?: string | null;
  status: DocumentStatus;
  error_message?: string | null;
  summary?: string | null;
  key_topics?: string[] | null;
  document_type?: string | null;
  tags?: string[] | null;
  folder_id?: string | null;
  num_pages?: number | null;
  num_chunks?: number | null;
  created_at: string;
  updated_at?: string | null;
  user_role?: AccessRole;
}

export interface Chunk {
  id: string;
  document_id: string;
  doc_name?: string;
  content: string;
  page_number?: number | null;
  section_heading?: string | null;
  score?: number;
  retrieval_score?: number;
  rerank_score?: number;
  final_score?: number;
}

export interface Citation {
  source?: number;
  document_id?: string;
  doc_id?: string;
  doc_name: string;
  page?: number | null;
  snippet: string;
  chunk_id: string;
}

export interface Message {
  id: string;
  conversation_id?: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  created_at?: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message?: string | null;
  last_message_at?: string | null;
}

export interface ConversationDetail extends Conversation {
  user_id: string;
  messages: Message[];
}

export interface SearchResult {
  id?: string;
  chunk_id?: string;
  document_id?: string;
  doc_id?: string;
  doc_name: string;
  page_number?: number | null;
  page?: number | null;
  content?: string;
  snippet?: string;
  final_score?: number;
  score?: number;
  retrieval_score?: number;
  rerank_score?: number;
  rrf_score?: number;
  signal_score?: number;
  file_path?: string | null;
  signed_url?: string | null;
  mime_type?: string | null;
  document_type?: string | null;
}

export interface SearchResponse {
  query: string;
  count: number;
  results: SearchResult[];
}

export interface Folder {
  id: string;
  user_id?: string;
  name: string;
  color: string;
  icon: string;
  sort_order?: number;
  created_at?: string;
  doc_count?: number;
}

export interface PermissionEntry {
  id: string;
  role: Exclude<AccessRole, "owner">;
  created_at: string;
  user_id: string;
  email: string;
  display_name?: string | null;
}

export interface SharedThreadResponse {
  title: string;
  messages: Message[];
  view_count: number;
  shared_at: string;
}

export type ChatStreamEvent =
  | { type: "token"; text: string }
  | { type: "done"; citations: Citation[]; title?: string }
  | { type: "error"; message: string };
