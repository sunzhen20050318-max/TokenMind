import React from 'react';
import type { CreativeCapabilitySettings } from '../types/config';
import { deriveCreativeCapabilityState } from './creativePageState';
import './creativePages.css';

interface CreativeWorkspacePageProps {
  capability: CreativeCapabilitySettings | null | undefined;
  title: string;
  eyebrow: string;
  description: string;
  configuredCopy: string;
  disabledCopy: string;
  enabledCopy: string;
}

const STATE_LABELS = {
  unconfigured: '未配置',
  'configured-disabled': '已配置，未启用',
  enabled: '已启用',
} as const;

export const CreativeWorkspacePage: React.FC<CreativeWorkspacePageProps> = ({
  capability,
  title,
  eyebrow,
  description,
  configuredCopy,
  disabledCopy,
  enabledCopy,
}) => {
  const state = deriveCreativeCapabilityState(capability);
  const summaryCopy =
    state === 'enabled'
      ? enabledCopy
      : state === 'configured-disabled'
        ? disabledCopy
        : configuredCopy;

  return (
    <section className="creative-workspace">
      <div className="creative-workspace__hero">
        <div className="creative-workspace__eyebrow">{eyebrow}</div>
        <h1 className="creative-workspace__title">{title}</h1>
        <p className="creative-workspace__description">{description}</p>
      </div>

      <div className="creative-workspace__grid">
        <article className={`creative-workspace__panel is-${state}`}>
          <div className="creative-workspace__panel-head">
            <span className="creative-workspace__panel-kicker">能力状态</span>
            <span className={`creative-workspace__status is-${state}`}>{STATE_LABELS[state]}</span>
          </div>
          <p className="creative-workspace__panel-copy">{summaryCopy}</p>
        </article>

        <article className="creative-workspace__panel">
          <div className="creative-workspace__panel-head">
            <span className="creative-workspace__panel-kicker">当前模型</span>
          </div>
          <div className="creative-workspace__facts">
            <div className="creative-workspace__fact">
              <span>Provider</span>
              <strong>{capability?.provider || '未配置'}</strong>
            </div>
            <div className="creative-workspace__fact">
              <span>Model</span>
              <strong>{capability?.model || '未配置'}</strong>
            </div>
          </div>
        </article>
      </div>

      <article className="creative-workspace__canvas">
        <div className="creative-workspace__canvas-art" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div className="creative-workspace__canvas-copy">
          <h2>入口已预留</h2>
        </div>
      </article>
    </section>
  );
};
