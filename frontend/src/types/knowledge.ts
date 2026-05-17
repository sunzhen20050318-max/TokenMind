export type KnowledgeBaseType = 'rag' | 'wiki';

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  type: KnowledgeBaseType;
  status: string;
  enabled: boolean;
  document_count: number;
  // Wiki-specific counts (default 0 for rag KBs)
  language: string;
  root_path: string;
  source_count: number;
  page_count: number;
  entity_count: number;
  topic_count: number;
  link_count: number;
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

export interface WikiPageSummary {
  title: string;
  type: 'source' | 'entity' | 'topic' | 'comparison' | 'synthesis' | 'query' | 'page';
  path: string;
}

export interface WikiPageListResponse {
  pages: WikiPageSummary[];
}

export interface WikiGraphNode {
  id: string;
  title: string;
  type: string;
  path: string;
  summary: string;
  degree: number;
}

export interface WikiGraphEdge {
  source: string;
  target: string;
  relation: string;
  weight: number;
}

export interface WikiGraphData {
  nodes: WikiGraphNode[];
  edges: WikiGraphEdge[];
  broken_links: { from: string; target: string }[];
  updated_at: string | null;
}

export function isWikiKb(kb: KnowledgeBase): boolean {
  return kb.type === 'wiki';
}

export function isRagKb(kb: KnowledgeBase): boolean {
  return kb.type === 'rag';
}
