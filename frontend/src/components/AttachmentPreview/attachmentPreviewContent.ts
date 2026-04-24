export type PreviewKind =
  | 'image'
  | 'markdown'
  | 'text'
  | 'pdf'
  | 'audio'
  | 'video'
  | 'unsupported';

const TEXT_MIME_PREFIXES = ['text/'];
const MARKDOWN_MIMES = new Set(['text/markdown', 'text/x-markdown']);
const EXTRA_TEXT_MIMES = new Set([
  'application/json',
  'application/xml',
  'application/x-yaml',
  'application/x-sh',
  'application/javascript',
  'application/x-python',
  'application/sql',
  'application/x-log',
]);

const TEXT_EXTENSIONS = new Set([
  'txt', 'log', 'csv', 'tsv', 'json', 'xml', 'yaml', 'yml', 'ini', 'conf', 'toml',
  'py', 'js', 'ts', 'tsx', 'jsx', 'mjs', 'cjs', 'sh', 'bash', 'zsh', 'rb', 'go',
  'rs', 'java', 'kt', 'swift', 'c', 'cpp', 'h', 'hpp', 'cs', 'sql', 'html', 'css',
  'scss', 'less', 'svg', 'dockerfile', 'env', 'gitignore',
]);

const MARKDOWN_EXTENSIONS = new Set(['md', 'markdown', 'mdown', 'mkdn']);

export function extractExtension(name: string | undefined | null): string {
  if (!name) return '';
  const dot = name.lastIndexOf('.');
  if (dot < 0 || dot === name.length - 1) return '';
  return name.slice(dot + 1).toLowerCase();
}

export function resolvePreviewKind(options: {
  mimeType?: string | null;
  name?: string | null;
  isImage?: boolean | null;
}): PreviewKind {
  const mime = (options.mimeType || '').toLowerCase();
  const ext = extractExtension(options.name);

  if (options.isImage || mime.startsWith('image/')) {
    return 'image';
  }
  if (mime === 'application/pdf' || ext === 'pdf') {
    return 'pdf';
  }
  if (mime.startsWith('audio/')) {
    return 'audio';
  }
  if (mime.startsWith('video/')) {
    return 'video';
  }
  if (MARKDOWN_MIMES.has(mime) || MARKDOWN_EXTENSIONS.has(ext)) {
    return 'markdown';
  }
  if (
    TEXT_MIME_PREFIXES.some((prefix) => mime.startsWith(prefix)) ||
    EXTRA_TEXT_MIMES.has(mime) ||
    TEXT_EXTENSIONS.has(ext)
  ) {
    return 'text';
  }
  return 'unsupported';
}

/** Decide whether the "source / rendered" toggle should be shown. */
export function canToggleRendered(kind: PreviewKind): boolean {
  return kind === 'markdown';
}

const COPY_FRIENDLY_KINDS: PreviewKind[] = ['markdown', 'text'];

export function canCopyContent(kind: PreviewKind): boolean {
  return COPY_FRIENDLY_KINDS.includes(kind);
}
