export type AnnouncementLevel = 'info' | 'warning' | 'critical';

export interface AnnouncementDownloads {
  macos?: string;
  windows?: string;
  linux?: string;
}

export interface LatestRelease {
  version: string;
  released_at?: string;
  release_notes?: string;
  downloads?: AnnouncementDownloads;
  /** Optional fallback URL when no per-OS download is provided. */
  download_page?: string;
  /** App versions older than this should be treated as obsolete. */
  min_supported_version?: string;
}

export interface Announcement {
  id: string;
  title: string;
  message: string;
  level?: AnnouncementLevel;
  /** ISO date or datetime; before this the announcement is hidden. */
  starts_at?: string;
  /** ISO date or datetime; after this the announcement is hidden. */
  expires_at?: string;
  /** Only show when current app version >= this. */
  min_version?: string;
  /** Only show when current app version <= this. */
  max_version?: string;
  /** Optional external link, opened in the user's browser. */
  link?: string;
}

export interface VersionInfo {
  schema_version: number;
  latest: LatestRelease;
  announcements: Announcement[];
}

/** Unified inbox-item shown in the bell panel. */
export type BellItemType = 'announcement' | 'version' | 'skill-suggestion';

export interface BellItem {
  id: string;
  type: BellItemType;
  title: string;
  message: string;
  level: AnnouncementLevel;
  /** Timestamp ms when this client first observed the item. Drives sort
   * order and the 15-day TTL cleanup. */
  receivedAt: number;
  /** Optional publication timestamp (ms). Used as a tiebreaker when several
   * items share the same receivedAt — typically on the first fetch where
   * everything in the JSON arrives simultaneously. */
  publishedAt?: number;
  isRead: boolean;
  /** External link (announcements). */
  link?: string;
  /** Per-OS download URL (version items). */
  downloadUrl?: string;
  /** Internal navigation hint — skill-suggestion items click into Settings.
   * Components map this to a callback rather than a URL. */
  navTarget?: 'skills';
}
