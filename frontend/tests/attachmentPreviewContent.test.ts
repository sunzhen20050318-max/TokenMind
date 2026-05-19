import test from 'node:test';
import assert from 'node:assert/strict';

import {
  resolvePreviewKind,
  extractExtension,
  canCopyContent,
  canToggleRendered,
} from '../src/components/AttachmentPreview/attachmentPreviewContent';

// --- office kind detection (the focus of this feature) ---------------------

test('xlsx by extension → office kind', () => {
  assert.equal(resolvePreviewKind({ name: 'report.xlsx' }), 'office');
});

test('docx by extension → office kind', () => {
  assert.equal(resolvePreviewKind({ name: 'contract.docx' }), 'office');
});

test('pptx by extension → office kind', () => {
  assert.equal(resolvePreviewKind({ name: 'deck.pptx' }), 'office');
});

test('legacy doc/xls/ppt → office kind', () => {
  assert.equal(resolvePreviewKind({ name: 'old.doc' }), 'office');
  assert.equal(resolvePreviewKind({ name: 'budget.xls' }), 'office');
  assert.equal(resolvePreviewKind({ name: 'pitch.ppt' }), 'office');
});

test('OpenDocument variants → office kind', () => {
  assert.equal(resolvePreviewKind({ name: 'notes.odt' }), 'office');
  assert.equal(resolvePreviewKind({ name: 'data.ods' }), 'office');
  assert.equal(resolvePreviewKind({ name: 'talk.odp' }), 'office');
});

test('rtf → office kind', () => {
  assert.equal(resolvePreviewKind({ name: 'memo.rtf' }), 'office');
});

test('OOXML MIME type with unknown extension still → office', () => {
  assert.equal(
    resolvePreviewKind({
      name: 'no-extension-here',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }),
    'office'
  );
});

test('msword MIME type → office', () => {
  assert.equal(
    resolvePreviewKind({ name: 'x', mimeType: 'application/msword' }),
    'office'
  );
});

test('case insensitive extension match', () => {
  assert.equal(resolvePreviewKind({ name: 'REPORT.XLSX' }), 'office');
  assert.equal(resolvePreviewKind({ name: 'Pitch.PPTX' }), 'office');
});

// --- non-office formats should NOT regress -------------------------------

test('png with image mime stays as image kind', () => {
  // The function detects images via MIME first; the backend always supplies
  // a mime_type for uploaded files. Filename-only is fine for office
  // extension fallback but not for images.
  assert.equal(
    resolvePreviewKind({ name: 'photo.png', mimeType: 'image/png' }),
    'image'
  );
});

test('pdf stays as pdf kind', () => {
  assert.equal(resolvePreviewKind({ name: 'paper.pdf' }), 'pdf');
});

test('csv stays as text kind (not office)', () => {
  // CSV is plain comma-separated text; the backend serves it inline.
  assert.equal(resolvePreviewKind({ name: 'data.csv' }), 'text');
});

test('md stays as markdown', () => {
  assert.equal(resolvePreviewKind({ name: 'readme.md' }), 'markdown');
});

test('unknown binary extension → unsupported', () => {
  assert.equal(resolvePreviewKind({ name: 'archive.7z' }), 'unsupported');
});

test('isImage flag wins over extension', () => {
  assert.equal(
    resolvePreviewKind({ name: 'oddly-named.xlsx', isImage: true }),
    'image'
  );
});

// --- extractExtension --------------------------------------------------------

test('extractExtension handles trailing dot, no dot, deep paths', () => {
  assert.equal(extractExtension('file.txt'), 'txt');
  assert.equal(extractExtension('no-extension'), '');
  assert.equal(extractExtension('trailing.'), '');
  assert.equal(extractExtension('a/b/c.tar.gz'), 'gz');
});

// --- toggle/copy helpers (canToggleRendered / canCopyContent) -----------------

test('office does NOT support the rendered/source toggle', () => {
  assert.equal(canToggleRendered('office'), false);
});

test('office cannot be copied as text', () => {
  assert.equal(canCopyContent('office'), false);
});
