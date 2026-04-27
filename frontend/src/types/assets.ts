export type AssetCategory = 'image' | 'video' | 'file';

export interface AssetItem {
  id: string;
  name: string;
  category: string;
  is_image: boolean;
  mime_type: string | null;
  size: number;
  session_id: string;
  project_id: string | null;
  created_at: string;
  favorite: boolean;
  storage_path: string;
  preview_text: string | null;
}

export interface AssetListResponse {
  items: AssetItem[];
  next_cursor: number | null;
  total: number;
}

export interface AssetActionResponse {
  success: boolean;
  id: string;
}
