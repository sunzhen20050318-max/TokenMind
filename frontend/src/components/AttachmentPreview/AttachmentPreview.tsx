import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../../services/api';
import { useChatStore } from '../../stores/chatStore';
import type { Attachment } from '../../types';
import { copyToClipboard } from '../../utils/clipboard';
import { OverlayPortal } from '../Overlay/OverlayPortal';
import {
  canCopyContent,
  canToggleRendered,
  extractExtension,
  resolvePreviewKind,
} from './attachmentPreviewContent';
import type { PreviewKind } from './attachmentPreviewContent';
import './attachmentPreview.css';

const TEXT_LIKE_LIMIT = 1024 * 1024; // 1MB cap for fetching raw text
const DRAWER_WIDTH_STORAGE_KEY = 'tokenmind:attachment-preview-width';
const DRAWER_MIN_PX = 360;
const DRAWER_MAX_RATIO = 0.95;
const DRAWER_DEFAULT_PX = 720;

function clampDrawerWidth(px: number, viewport: number): number {
  const max = Math.max(DRAWER_MIN_PX + 40, Math.floor(viewport * DRAWER_MAX_RATIO));
  return Math.min(max, Math.max(DRAWER_MIN_PX, Math.round(px)));
}

function loadStoredDrawerWidth(): number | null {
  try {
    const raw = window.localStorage.getItem(DRAWER_WIDTH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) && parsed >= DRAWER_MIN_PX ? parsed : null;
  } catch {
    return null;
  }
}

function formatSize(size?: number): string | null {
  if (typeof size !== 'number' || size <= 0) return null;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

function subtitleFor(attachment: Attachment, kind: PreviewKind): string {
  const ext = extractExtension(attachment.name);
  const parts: string[] = [];
  if (ext) {
    parts.push(ext.toUpperCase());
  } else {
    const map: Record<PreviewKind, string> = {
      image: '图片',
      markdown: 'Markdown',
      text: '文本',
      pdf: 'PDF',
      audio: '音频',
      video: '视频',
      office: 'Office',
      unsupported: '附件',
    };
    parts.push(map[kind]);
  }
  const size = formatSize(attachment.size);
  if (size) parts.push(size);
  return parts.join(' · ');
}

export function AttachmentPreview() {
  const attachment = useChatStore((state) => state.previewAttachment);
  const close = useChatStore((state) => state.closeAttachmentPreview);
  const [textContent, setTextContent] = useState<string | null>(null);
  const [textError, setTextError] = useState<string | null>(null);
  const [textLoading, setTextLoading] = useState<boolean>(false);
  const [viewMode, setViewMode] = useState<'rendered' | 'source'>('rendered');
  const [copied, setCopied] = useState<boolean>(false);
  const [drawerWidth, setDrawerWidth] = useState<number>(() => {
    if (typeof window === 'undefined') return DRAWER_DEFAULT_PX;
    const stored = loadStoredDrawerWidth();
    return clampDrawerWidth(stored ?? DRAWER_DEFAULT_PX, window.innerWidth || DRAWER_DEFAULT_PX);
  });
  const [isResizing, setIsResizing] = useState<boolean>(false);
  const resizeStartRef = useRef<{ startX: number; startWidth: number }>({ startX: 0, startWidth: 0 });

  const href = useMemo(() => {
    if (!attachment) return null;
    if (attachment.id) return api.getAttachmentUrl(attachment.id);
    return attachment.path ?? null;
  }, [attachment]);

  // Inline variant: used by the iframe / media / fetch logic so the server serves
  // the file without Content-Disposition: attachment (which would force a download
  // and leave the <iframe> body empty).
  const inlineHref = useMemo(() => {
    if (!attachment?.id) return href;
    return `${api.getAttachmentUrl(attachment.id)}?disposition=inline`;
  }, [attachment, href]);

  // Office files (docx/xlsx/pptx/...) go through the /preview endpoint
  // which lazily converts them to PDF via soffice. For other kinds the
  // existing inline URL is used.
  const previewHref = useMemo(() => {
    if (!attachment?.id) return inlineHref;
    return api.getAttachmentPreviewUrl(attachment.id);
  }, [attachment, inlineHref]);

  const [officeState, setOfficeState] = useState<'idle' | 'loading' | 'ready' | 'missing-soffice' | 'failed'>('idle');

  const kind = useMemo<PreviewKind>(() => {
    if (!attachment) return 'unsupported';
    return resolvePreviewKind({
      mimeType: attachment.mime_type,
      name: attachment.name,
      isImage: attachment.is_image,
    });
  }, [attachment]);

  const subtitle = attachment ? subtitleFor(attachment, kind) : '';

  // Reset transient state when the selected attachment changes
  useEffect(() => {
    setTextContent(null);
    setTextError(null);
    setTextLoading(false);
    setViewMode(kind === 'markdown' ? 'rendered' : 'source');
    setCopied(false);
    setOfficeState('idle');
  }, [attachment?.id, attachment?.path, kind]);

  // For office files, do a HEAD probe against the /preview endpoint before
  // pointing an iframe at it. That way we surface a friendly "需要装
  // LibreOffice" message instead of an empty iframe when the backend
  // returns 503 / 502 / 504.
  useEffect(() => {
    if (!attachment || kind !== 'office' || !attachment.id) return;
    let cancelled = false;
    setOfficeState('loading');
    (async () => {
      try {
        const response = await fetch(api.getAttachmentPreviewUrl(attachment.id!), { method: 'HEAD' });
        if (cancelled) return;
        if (response.ok) {
          setOfficeState('ready');
        } else if (response.status === 503) {
          setOfficeState('missing-soffice');
        } else {
          setOfficeState('failed');
        }
      } catch {
        if (!cancelled) setOfficeState('failed');
      }
    })();
    return () => { cancelled = true; };
  }, [attachment, kind]);

  // Fetch text/markdown content on demand
  useEffect(() => {
    if (!attachment || !inlineHref) return;
    if (kind !== 'text' && kind !== 'markdown') return;
    let cancelled = false;
    setTextLoading(true);
    setTextError(null);
    (async () => {
      try {
        const response = await fetch(inlineHref);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const contentLength = Number(response.headers.get('Content-Length') || '0');
        if (contentLength && contentLength > TEXT_LIKE_LIMIT) {
          throw new Error('文件太大，无法预览');
        }
        const text = await response.text();
        if (!cancelled) {
          if (text.length > TEXT_LIKE_LIMIT) {
            setTextContent(text.slice(0, TEXT_LIKE_LIMIT));
            setTextError('文件超过 1MB，只展示前 1MB 内容');
          } else {
            setTextContent(text);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setTextError(err instanceof Error ? err.message : '加载失败');
        }
      } finally {
        if (!cancelled) {
          setTextLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attachment, inlineHref, kind]);

  // Close on Esc
  useEffect(() => {
    if (!attachment) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        close();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [attachment, close]);

  // Drag-to-resize: grab the left edge and drag to grow/shrink the drawer.
  useEffect(() => {
    if (!isResizing) return;
    const handleMove = (event: MouseEvent) => {
      const { startX, startWidth } = resizeStartRef.current;
      const deltaX = event.clientX - startX;
      // Drawer is anchored to the right: dragging left grows the width.
      const next = clampDrawerWidth(startWidth - deltaX, window.innerWidth);
      setDrawerWidth(next);
    };
    const handleUp = () => {
      setIsResizing(false);
      try {
        window.localStorage.setItem(DRAWER_WIDTH_STORAGE_KEY, String(drawerWidth));
      } catch {
        // ignore
      }
    };
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [isResizing, drawerWidth]);

  // Keep width valid when the viewport shrinks.
  useEffect(() => {
    const handleResize = () => {
      setDrawerWidth((current) => clampDrawerWidth(current, window.innerWidth));
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleCopy = useCallback(async () => {
    const content = textContent ?? attachment?.preview_text ?? '';
    if (!content) return;
    const ok = await copyToClipboard(content);
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } else {
      setTextError('复制失败');
    }
  }, [attachment?.preview_text, textContent]);

  if (!attachment) {
    return null;
  }

  const toggleAvailable = canToggleRendered(kind);
  const copyAvailable = canCopyContent(kind) && !!(textContent ?? attachment.preview_text);

  return (
    <OverlayPortal>
      <div
        className="attachment-preview__overlay"
        role="dialog"
        aria-modal="true"
        aria-label={`预览 ${attachment.name}`}
      >
        <div
          className="attachment-preview__backdrop"
          onClick={close}
          aria-hidden="true"
        />
        <aside
          className={`attachment-preview__drawer ${isResizing ? 'is-resizing' : ''}`}
          style={{ width: drawerWidth }}
        >
          <div
            className={`attachment-preview__resizer ${isResizing ? 'is-active' : ''}`}
            role="separator"
            aria-orientation="vertical"
            aria-label="拖动调整预览窗口宽度"
            onMouseDown={(event) => {
              event.preventDefault();
              resizeStartRef.current = {
                startX: event.clientX,
                startWidth: drawerWidth,
              };
              setIsResizing(true);
            }}
            onDoubleClick={() =>
              setDrawerWidth(clampDrawerWidth(DRAWER_DEFAULT_PX, window.innerWidth))
            }
          >
            <span className="attachment-preview__resizer-handle" />
          </div>
          <header className="attachment-preview__header">
            <div className="attachment-preview__title">
              {toggleAvailable ? (
                <div className="attachment-preview__toggle" role="tablist">
                  <button
                    type="button"
                    className={`attachment-preview__toggle-btn ${viewMode === 'rendered' ? 'is-active' : ''}`}
                    onClick={() => setViewMode('rendered')}
                    aria-label="渲染视图"
                    title="渲染视图"
                  >
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    className={`attachment-preview__toggle-btn ${viewMode === 'source' ? 'is-active' : ''}`}
                    onClick={() => setViewMode('source')}
                    aria-label="源代码"
                    title="源代码"
                  >
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="m16 18 6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="m8 6-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                </div>
              ) : null}
              <div className="attachment-preview__title-text">
                <strong>{attachment.name}</strong>
                {subtitle ? <span>{subtitle}</span> : null}
              </div>
            </div>
            <div className="attachment-preview__actions">
              {copyAvailable ? (
                <button
                  type="button"
                  className="attachment-preview__action"
                  onClick={() => void handleCopy()}
                  disabled={textLoading}
                >
                  {copied ? '已复制' : '复制'}
                </button>
              ) : null}
              {href ? (
                <a
                  className="attachment-preview__action"
                  href={href}
                  download={attachment.name}
                  target="_blank"
                  rel="noreferrer"
                  // For office files the iframe shows a *converted* PDF — to
                  // avoid confusion with Chrome's PDF toolbar download (which
                  // would download the PDF, not the source), label this button
                  // with the original extension.
                  title={
                    kind === 'office'
                      ? `下载源文件 (.${extractExtension(attachment.name)})`
                      : '下载'
                  }
                >
                  {kind === 'office'
                    ? `下载源文件 (.${extractExtension(attachment.name) || 'xlsx'})`
                    : '下载'}
                </a>
              ) : null}
              <button
                type="button"
                className="attachment-preview__close"
                onClick={close}
                aria-label="关闭预览"
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="m6 6 12 12M18 6 6 18" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          </header>

          <div className="attachment-preview__body">
            {href == null ? (
              <div className="attachment-preview__fallback">
                <strong>附件不可用</strong>
                <p>这个附件没有可访问的 URL，无法预览。</p>
              </div>
            ) : kind === 'image' ? (
              <div className="attachment-preview__image-wrap">
                <img src={inlineHref ?? undefined} alt={attachment.name} />
              </div>
            ) : kind === 'pdf' ? (
              <iframe
                className="attachment-preview__iframe"
                // Chrome's PDF viewer hint: hide thumbnail sidebar and fit width by default.
                src={inlineHref ? `${inlineHref}#toolbar=1&navpanes=0&view=FitH` : undefined}
                title={attachment.name}
              />
            ) : kind === 'office' ? (
              officeState === 'loading' || officeState === 'idle' ? (
                <div className="attachment-preview__loading">正在准备 Office 预览…</div>
              ) : officeState === 'ready' ? (
                <iframe
                  className="attachment-preview__iframe"
                  src={previewHref ? `${previewHref}#toolbar=1&navpanes=0&view=FitH` : undefined}
                  title={attachment.name}
                />
              ) : officeState === 'missing-soffice' ? (
                <div className="attachment-preview__fallback">
                  <strong>需要安装 LibreOffice 才能预览 Office 文件</strong>
                  <p>
                    安装方式: <code>brew install libreoffice</code>(macOS) 或 <code>apt install libreoffice</code>(Linux),
                    装好后刷新页面即可。
                  </p>
                  <p>暂时可以点右上角"下载"用本地 Office 应用打开。</p>
                </div>
              ) : (
                <div className="attachment-preview__fallback">
                  <strong>预览生成失败</strong>
                  <p>转换过程出错,点右上角"下载"用本地应用打开。</p>
                </div>
              )
            ) : kind === 'audio' ? (
              <div className="attachment-preview__media">
                <audio controls src={inlineHref ?? undefined} style={{ width: '100%' }} />
              </div>
            ) : kind === 'video' ? (
              <div className="attachment-preview__media">
                <video controls src={inlineHref ?? undefined} style={{ width: '100%' }} />
              </div>
            ) : kind === 'markdown' || kind === 'text' ? (
              <div className="attachment-preview__text-wrap">
                {textLoading && textContent == null ? (
                  <div className="attachment-preview__loading">正在加载内容…</div>
                ) : textError && textContent == null ? (
                  <div className="attachment-preview__fallback">
                    <strong>预览失败</strong>
                    <p>{textError}</p>
                  </div>
                ) : kind === 'markdown' && viewMode === 'rendered' ? (
                  <article className="attachment-preview__markdown">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {textContent ?? ''}
                    </ReactMarkdown>
                    {textError ? (
                      <div className="attachment-preview__hint">{textError}</div>
                    ) : null}
                  </article>
                ) : (
                  <>
                    <pre className="attachment-preview__source">
                      <code>{textContent ?? ''}</code>
                    </pre>
                    {textError ? (
                      <div className="attachment-preview__hint">{textError}</div>
                    ) : null}
                  </>
                )}
              </div>
            ) : (
              <div className="attachment-preview__fallback">
                <strong>暂不支持这种文件的内联预览</strong>
                <p>
                  请使用右上角的"下载"保存到本地打开。
                  {attachment.preview_text ? '以下是文件里的文本摘要：' : ''}
                </p>
                {attachment.preview_text ? (
                  <pre className="attachment-preview__source">
                    <code>{attachment.preview_text}</code>
                  </pre>
                ) : null}
              </div>
            )}
          </div>
        </aside>
      </div>
    </OverlayPortal>
  );
}
