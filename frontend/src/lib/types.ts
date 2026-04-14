export interface User {
  id: string;
  email: string;
  displayName?: string;
}

export interface Document {
  id: string;
  name: string;
  status: "uploaded" | "processing" | "indexed" | "error";
  num_pages?: number;
  num_chunks?: number;
  summary?: string;
  key_topics?: string[];
  document_type?: string;
  tags?: string[];
  folder_id?: string;
  created_at: string;
}

export interface Chunk {
  id: string;
  document_id: string;
  content: string;
  page_number?: number;
  section_heading?: string;
}

export interface Citation {
  doc_id: string;
  doc_name: string;
  page: number;
  snippet: string;
  chunk_id: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface SearchResult {
  chunk_id: string;
  doc_id: string;
  doc_name: string;
  page: number;
  snippet: string;
  score: number;
}

export interface Folder {
  id: string;
  name: string;
  color: string;
  icon: string;
  doc_count?: number;
}
