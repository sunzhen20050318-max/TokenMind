import test from 'node:test';
import assert from 'node:assert/strict';

import type { Message } from '../src/types';
import {
  extractTextContent,
  inferLegacyCitations,
  resolveVisibleCitations,
} from '../src/components/Chat/messageBubbleContent';

test('extractTextContent strips linked knowledge metadata and keeps the user prompt', () => {
  const content = [
    '[Linked Knowledge - retrieved context only, not user text]',
    '60',
    '60',
    '[/Linked Knowledge]',
    'If the retrieved context is not relevant, say so instead of forcing it into the answer.',
    '我的学号是230200496',
  ].join('\n');

  assert.equal(extractTextContent(content, undefined), '我的学号是230200496');
});

test('inferLegacyCitations extracts legacy source cards for old knowledge replies', () => {
  const message: Message = {
    role: 'assistant',
    content: '根据检索到的 **25年12月德育测评表.xlsx** 内容，我查了一下。',
  };

  const citations = inferLegacyCitations(message, String(message.content));
  assert.equal(citations.length, 1);
  assert.equal(citations[0].document_name, '25年12月德育测评表.xlsx');
});

test('resolveVisibleCitations prefers structured citations when present', () => {
  const message: Message = {
    role: 'assistant',
    content: '这是新的回复',
    citations: [
      {
        knowledge_base_name: '测试知识库',
        document_name: '资料.pdf',
        excerpt: '命中的片段',
      },
    ],
  };

  const citations = resolveVisibleCitations(message, String(message.content));
  assert.equal(citations.length, 1);
  assert.equal(citations[0].document_name, '资料.pdf');
});

test('extractTextContent hides attachment helper copy when an attachment card exists', () => {
  const rendered = extractTextContent(
    '已发送！点击链接即可下载 empty_file.txt',
    [
      {
        id: 'att_1',
        name: 'empty_file.txt',
        origin: 'assistant_generated',
        status: 'temporary',
        is_image: false,
      },
    ]
  );

  assert.equal(rendered, '\u200b');
});

test('extractTextContent keeps normal assistant text alongside attachment cards', () => {
  const rendered = extractTextContent(
    '我已经帮你整理好了，下面是文件。',
    [
      {
        id: 'att_2',
        name: 'report.csv',
        origin: 'assistant_generated',
        status: 'temporary',
        is_image: false,
      },
    ]
  );

  assert.equal(rendered, '我已经帮你整理好了，下面是文件。');
});
