import React from 'react';
import type { CreativeCapabilitySettings } from '../types/config';
import { CreativeWorkspacePage } from './CreativeWorkspacePage';

export const VideoPage: React.FC<{ capability: CreativeCapabilitySettings | null | undefined }> = ({
  capability,
}) => (
  <CreativeWorkspacePage
    capability={capability}
    eyebrow="创作能力"
    title="视频"
    description="这里会承载独立的视频生成入口，后续可以在这里扩展镜头、时长和风格控制。"
    configuredCopy="还没有配置视频模型，请先到设置中心的创作能力里完成配置。"
    disabledCopy="视频模型已经配置完成，但当前还没有启用。"
    enabledCopy="视频能力已经就绪，后续版本会在这里接入实际生成流程。"
  />
);
