export interface StorageFileReference {
  session_id: string;
  title: string;
}

export interface StorageFileItem {
  name: string;
  stored_name: string;
  path: string;
  size: number;
  mime_type?: string | null;
  category: string;
  is_image: boolean;
  modified_at: string;
  created_at: string;
  referenced: boolean;
  reference_count: number;
  referenced_by: StorageFileReference[];
  can_delete: boolean;
}

export interface StorageSummary {
  used_bytes: number;
  quota_bytes: number;
  available_bytes: number;
  max_file_bytes: number;
  file_count: number;
  referenced_file_count: number;
  unreferenced_file_count: number;
  stale_unreferenced_file_count: number;
  retention_days: number;
  cleanup_interval_hours: number;
}

export interface StorageOverviewResponse {
  summary: StorageSummary;
  files: StorageFileItem[];
}

export interface StorageCleanupResponse {
  success: boolean;
  deleted_files: number;
  deleted_dirs: number;
}

export interface DeleteStorageFileResponse {
  success: boolean;
  path: string;
  deleted_bytes: number;
}
