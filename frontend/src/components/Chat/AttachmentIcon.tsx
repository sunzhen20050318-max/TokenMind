import type { Attachment } from '../../types';

type IconKind =
  | 'markdown'
  | 'pdf'
  | 'code'
  | 'spreadsheet'
  | 'archive'
  | 'audio'
  | 'video'
  | 'image'
  | 'text'
  | 'doc'
  | 'default';

const EXT_MAP: Record<string, IconKind> = {
  md: 'markdown',
  markdown: 'markdown',
  mdown: 'markdown',
  mkdn: 'markdown',
  pdf: 'pdf',
  json: 'code',
  yaml: 'code',
  yml: 'code',
  toml: 'code',
  xml: 'code',
  html: 'code',
  css: 'code',
  scss: 'code',
  less: 'code',
  js: 'code',
  jsx: 'code',
  ts: 'code',
  tsx: 'code',
  mjs: 'code',
  cjs: 'code',
  py: 'code',
  rb: 'code',
  go: 'code',
  rs: 'code',
  java: 'code',
  kt: 'code',
  swift: 'code',
  c: 'code',
  cpp: 'code',
  h: 'code',
  hpp: 'code',
  cs: 'code',
  sh: 'code',
  bash: 'code',
  zsh: 'code',
  sql: 'code',
  csv: 'spreadsheet',
  tsv: 'spreadsheet',
  xlsx: 'spreadsheet',
  xls: 'spreadsheet',
  ods: 'spreadsheet',
  zip: 'archive',
  tar: 'archive',
  gz: 'archive',
  bz2: 'archive',
  '7z': 'archive',
  rar: 'archive',
  mp3: 'audio',
  wav: 'audio',
  ogg: 'audio',
  m4a: 'audio',
  flac: 'audio',
  aac: 'audio',
  opus: 'audio',
  mp4: 'video',
  mov: 'video',
  webm: 'video',
  mkv: 'video',
  avi: 'video',
  png: 'image',
  jpg: 'image',
  jpeg: 'image',
  gif: 'image',
  webp: 'image',
  svg: 'image',
  bmp: 'image',
  txt: 'text',
  log: 'text',
  ini: 'text',
  conf: 'text',
  env: 'text',
  doc: 'doc',
  docx: 'doc',
  rtf: 'doc',
  ppt: 'doc',
  pptx: 'doc',
};

function extOf(name?: string | null): string {
  if (!name) return '';
  const idx = name.lastIndexOf('.');
  if (idx < 0 || idx === name.length - 1) return '';
  return name.slice(idx + 1).toLowerCase();
}

export function resolveAttachmentIconKind(attachment: Attachment): IconKind {
  if (attachment.is_image) return 'image';
  const mime = (attachment.mime_type || '').toLowerCase();
  if (mime.startsWith('image/')) return 'image';
  if (mime.startsWith('audio/')) return 'audio';
  if (mime.startsWith('video/')) return 'video';
  if (mime === 'application/pdf') return 'pdf';
  if (mime === 'text/markdown' || mime === 'text/x-markdown') return 'markdown';

  const ext = extOf(attachment.name);
  if (ext in EXT_MAP) return EXT_MAP[ext];

  if (mime.startsWith('text/')) return 'text';
  return 'default';
}

interface AttachmentIconProps {
  attachment: Attachment;
  size?: number;
}

/**
 * Monochrome SVG icon tuned to the chat card background. Each variant uses the
 * same "paper" outline and swaps the inner glyph based on file category so the
 * visual vocabulary stays consistent with the rest of the UI.
 */
export function AttachmentIcon({ attachment, size = 22 }: AttachmentIconProps) {
  const kind = resolveAttachmentIconKind(attachment);

  const baseProps = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.6,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  };

  // Shared paper outline used as the frame for every variant.
  const Paper = (
    <>
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M14 3v4h4" />
    </>
  );

  if (kind === 'markdown') {
    return (
      <svg {...baseProps}>
        {Paper}
        <path d="M8 16v-4l2 2 2-2v4" />
        <path d="M15 12v4m0 0l-1-1m1 1l1-1" />
      </svg>
    );
  }

  if (kind === 'pdf') {
    return (
      <svg {...baseProps}>
        {Paper}
        <text
          x="8"
          y="18"
          fontSize="4.2"
          fontFamily="-apple-system, 'Helvetica Neue', Arial, sans-serif"
          fontWeight="700"
          fill="currentColor"
          stroke="none"
        >
          PDF
        </text>
      </svg>
    );
  }

  if (kind === 'code') {
    return (
      <svg {...baseProps}>
        {Paper}
        <path d="m10 13-2 2 2 2" />
        <path d="m14 13 2 2-2 2" />
      </svg>
    );
  }

  if (kind === 'spreadsheet') {
    return (
      <svg {...baseProps}>
        {Paper}
        <path d="M7 13h11" />
        <path d="M7 17h11" />
        <path d="M11 13v6" />
        <path d="M15 13v6" />
      </svg>
    );
  }

  if (kind === 'archive') {
    return (
      <svg {...baseProps}>
        {Paper}
        <path d="M12 8v2" />
        <path d="M12 12v2" />
        <path d="M12 16h1v2h-2v-2z" />
      </svg>
    );
  }

  if (kind === 'audio') {
    return (
      <svg {...baseProps}>
        {Paper}
        <path d="M10 12v6" />
        <circle cx="9" cy="18" r="1.5" />
        <path d="M14 12v4" />
        <circle cx="13" cy="16" r="1.5" />
        <path d="M10 12h4" />
      </svg>
    );
  }

  if (kind === 'video') {
    return (
      <svg {...baseProps}>
        {Paper}
        <path d="m10 13 5 3-5 3z" fill="currentColor" stroke="none" />
      </svg>
    );
  }

  if (kind === 'image') {
    return (
      <svg {...baseProps}>
        {Paper}
        <circle cx="10" cy="13" r="1.5" />
        <path d="m7 19 4-4 2 2 2-2 3 3" />
      </svg>
    );
  }

  if (kind === 'text') {
    return (
      <svg {...baseProps}>
        {Paper}
        <path d="M8 13h8" />
        <path d="M8 16h8" />
        <path d="M8 19h5" />
      </svg>
    );
  }

  if (kind === 'doc') {
    return (
      <svg {...baseProps}>
        {Paper}
        <path d="M8 13h8" />
        <path d="M8 16h8" />
        <path d="M8 19h4" />
      </svg>
    );
  }

  return (
    <svg {...baseProps}>
      {Paper}
    </svg>
  );
}
