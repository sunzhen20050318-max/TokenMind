import type { Attachment, Message, MessageCitation } from '../../types';

const ATTACHMENTS_TAG = '[Attached Files';
const KNOWLEDGE_TAG = '[Linked Knowledge';
const KNOWLEDGE_END_TAG = '[/Linked Knowledge]';
const KNOWLEDGE_TRAILER =
  'If the retrieved context is not relevant, say so instead of forcing it into the answer.';
const KNOWLEDGE_TRAILER_PATTERN =
  /If the retrieved context is not relevant,\s*say so instead of forcing it into the answer\.\s*/i;
const LEGACY_SOURCE_PATTERNS = [
  /根据检索到的\s+\*\*([^*]+)\*\*/g,
  /根据\s+\*\*([^*]+)\*\*[^:\n：]*/g,
  /根据\s+([^\n*]+?\.(?:pdf|docx?|xlsx?|pptx?|md|txt|csv|json))/gi,
];

export function stripKnowledgeMetadata(text: string): string {
  let sanitized = text;

  const taggedBlockStart = sanitized.indexOf(KNOWLEDGE_TAG);
  if (taggedBlockStart !== -1) {
    const taggedBlockEnd = sanitized.indexOf(KNOWLEDGE_END_TAG, taggedBlockStart);
    if (taggedBlockEnd !== -1) {
      sanitized =
        sanitized.slice(0, taggedBlockStart) +
        sanitized.slice(taggedBlockEnd + KNOWLEDGE_END_TAG.length);
    }
  }

  const trailerMatch = KNOWLEDGE_TRAILER_PATTERN.exec(sanitized);
  if (trailerMatch) {
    const remainder = sanitized.slice(trailerMatch.index + trailerMatch[0].length).trim();
    sanitized = remainder || '';
  }

  if (sanitized.startsWith(KNOWLEDGE_TAG)) {
    const endIndex = sanitized.indexOf(KNOWLEDGE_END_TAG);
    if (endIndex !== -1) {
      sanitized = sanitized.slice(endIndex + KNOWLEDGE_END_TAG.length).trim();
    }
  }

  return sanitized;
}

export function inferLegacyCitations(message: Message, renderedContent: string): MessageCitation[] {
  if (message.role !== 'assistant' || (message.citations && message.citations.length > 0)) {
    return [];
  }

  const rawContent =
    typeof message.content === 'string'
      ? message.content
      : Array.isArray(message.content)
        ? message.content
            .map((item) =>
              item && typeof item === 'object' && typeof item.text === 'string' ? item.text : ''
            )
            .join('\n')
        : renderedContent;

  const discovered = new Set<string>();
  const fallback: MessageCitation[] = [];
  for (const pattern of LEGACY_SOURCE_PATTERNS) {
    pattern.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(rawContent)) !== null) {
      const documentName = (match[1] || '')
        .trim()
        .replace(/[：，。,.\-—\s]+$/g, '')
        .replace(/^\*+|\*+$/g, '');
      if (!documentName || discovered.has(documentName)) {
        continue;
      }
      discovered.add(documentName);
      fallback.push({
        knowledge_base_name: '已链接知识库',
        document_name: documentName,
        excerpt: '这条旧回复没有保存结构化引用摘录。重新提问一次后，会显示更精确的来源片段。',
      });
      if (fallback.length >= 3) {
        return fallback;
      }
    }
  }
  return fallback;
}

export function resolveVisibleCitations(
  message: Message,
  renderedContent: string
): MessageCitation[] {
  if (message.citations && message.citations.length > 0) {
    return message.citations;
  }
  return inferLegacyCitations(message, renderedContent);
}

export function extractTextContent(
  content: Message['content'],
  attachments: Attachment[] | undefined
): string {
  const hidePlaceholderPaths = new Set((attachments || []).map((item) => item.path));

  const filterLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) {
      return false;
    }
    if (trimmed.startsWith(ATTACHMENTS_TAG)) {
      return false;
    }
    if (trimmed.startsWith(KNOWLEDGE_TAG) || trimmed === KNOWLEDGE_END_TAG) {
      return false;
    }
    if (trimmed === KNOWLEDGE_TRAILER) {
      return false;
    }
    if (trimmed === 'Attached files are available in the workspace:') {
      return false;
    }
    if (trimmed.startsWith('Use read_file for text-based files when possible.')) {
      return false;
    }
    if (trimmed.startsWith('- ') && attachments?.some((item) => trimmed.includes(item.path))) {
      return false;
    }
    if (/^\[(image|file): .+\]$/.test(trimmed)) {
      const path = trimmed.slice(trimmed.indexOf(':') + 1, -1).trim();
      if (hidePlaceholderPaths.has(path)) {
        return false;
      }
    }
    return true;
  };

  if (typeof content === 'string') {
    return stripKnowledgeMetadata(content)
      .split('\n')
      .filter(filterLine)
      .join('\n')
      .trim();
  }

  if (Array.isArray(content)) {
    return content
      .map((item) =>
        item && typeof item === 'object' && typeof item.text === 'string'
          ? stripKnowledgeMetadata(item.text)
          : ''
      )
      .flatMap((text) => text.split('\n'))
      .filter(filterLine)
      .join('\n')
      .trim();
  }

  return '';
}
