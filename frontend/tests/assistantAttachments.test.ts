import test from 'node:test';
import assert from 'node:assert/strict';
import { useChatStore } from '../src/stores/chatStore';

const INITIAL_STATE = useChatStore.getState();

test('finishStreamingAssistant stores assistant attachments on the streaming message', () => {
  useChatStore.setState(INITIAL_STATE, true);

  useChatStore.getState().startStreamingAssistant();
  useChatStore.getState().appendStreamingAssistant('已生成文件。');
  useChatStore.getState().finishStreamingAssistant('已生成文件。', undefined, [
    {
      id: 'att_1',
      name: 'summary.md',
      category: 'markdown',
      origin: 'assistant_generated',
      status: 'temporary',
      is_image: false,
    },
  ]);

  const lastMessage = useChatStore.getState().messages.at(-1);
  assert.equal(lastMessage?.role, 'assistant');
  assert.equal(lastMessage?.attachments?.[0]?.id, 'att_1');
  assert.equal(lastMessage?.attachments?.[0]?.status, 'temporary');
});

test('updateAttachment patches matching assistant attachment status in message history', () => {
  useChatStore.setState(
    {
      ...INITIAL_STATE,
      messages: [
        {
          role: 'assistant',
          content: '这里是文件。',
          attachments: [
            {
              id: 'att_2',
              name: 'report.csv',
              category: 'spreadsheet',
              origin: 'assistant_generated',
              status: 'temporary',
              is_image: false,
            },
          ],
        },
      ],
    },
    true
  );

  useChatStore.getState().updateAttachment('att_2', {
    id: 'att_2',
    name: 'report.csv',
    category: 'spreadsheet',
    origin: 'assistant_generated',
    status: 'saved',
    is_image: false,
  });

  const attachment = useChatStore.getState().messages[0].attachments?.[0];
  assert.equal(attachment?.status, 'saved');
});
