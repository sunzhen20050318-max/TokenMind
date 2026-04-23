import React from 'react';
import type { CreativeCapabilitySettings } from '../types/config';
import { CreativeWorkspacePage } from './CreativeWorkspacePage';

export const VoiceClonePage: React.FC<{ capability: CreativeCapabilitySettings | null | undefined }> = ({
  capability,
}) => (
  <CreativeWorkspacePage
    capability={capability}
    eyebrow="创作能力"
    title="声音克隆"
    description="这里会承载独立的声音克隆入口，用来管理语音风格和角色音色。"
    configuredCopy="还没有配置声音克隆模型，请先到设置中心的创作能力里完成配置。"
    disabledCopy="声音克隆模型已经配置完成，但当前还没有启用。"
    enabledCopy="声音克隆能力已经就绪，后续版本会在这里接入实际生成流程。"
  />
);
