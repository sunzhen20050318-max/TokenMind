export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  status: string;
  enabled: boolean;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDocument {
  id: string;
  knowledge_base_id: string;
  name: string;
  path: string;
  file_type: string;
  size: number;
  status: string;
  processing_stage: string;
  processing_progress: number;
  error_message?: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeOverviewResponse {
  items: KnowledgeBase[];
}

export interface KnowledgeDetailResponse {
  knowledge_base: KnowledgeBase;
  documents: KnowledgeDocument[];
}
