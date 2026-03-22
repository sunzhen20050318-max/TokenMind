import { useState, useEffect, useRef } from 'react';
import { useChatStore } from '../stores/chatStore';

// Default model per provider when the provider's own defaultModel is not set
const PROVIDER_DEFAULT_MODELS: Record<string, string> = {
  deepseek: 'deepseek-chat',
  minimax: 'MiniMax-M2.7',
  anthropic: 'claude-sonnet-4-5',
  openai: 'gpt-4o',
  openrouter: 'anthropic/claude-sonnet-4-5',
  gemini: 'gemini-2.0-flash',
  zhipu: 'glm-4',
  dashscope: 'qwen-max',
  moonshot: 'kimi-k2.5',
  groq: 'llama-3.3-70b-versatile',
  siliconflow: 'Qwen/Qwen2.5-7B-Instruct',
  volcengine: 'doubao-1-5-pro-32k',
  aihubmix: 'anthropic/claude-sonnet-4-5',
  ollama: 'llama3.2',
  vllm: 'llama-3.1-8b-instruct',
};

export interface ProviderConfig {
  id: string;
  name: string;
  configured: boolean;
  apiBase: string;
  apiKeyMasked: string;
  enabled?: boolean;
}

interface ModelConfigPageProps {
  model: ProviderConfig;
  onBack: () => void;
  onSave: (id: string, apiKey: string, apiBase: string) => void;
}

const ModelConfigPage: React.FC<ModelConfigPageProps> = ({ model, onBack, onSave }) => {
  const [apiBase, setApiBase] = useState(model.apiBase || '');
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    setApiBase(model.apiBase || '');
    setApiKey('');
    setShowKey(false);
  }, [model.id]);

  const handleSave = () => {
    onSave(model.id, apiKey, apiBase);
    onBack();
  };

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        width: '100%',
        height: '100%',
        backgroundColor: '#1c1c1e',
        display: 'flex',
        flexDirection: 'column',
        animation: 'slideIn 0.25s ease-out',
      }}
    >
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>

      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '16px 24px',
          borderBottom: '1px solid #333',
          flexShrink: 0,
        }}
      >
        <button
          onClick={onBack}
          style={{
            background: 'none',
            border: 'none',
            color: '#a0a0a0',
            cursor: 'pointer',
            padding: '4px 8px',
            fontSize: '14px',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          返回
        </button>
        <div style={{ color: '#e5e5e5', fontSize: '16px', fontWeight: 600 }}>{model.name}</div>
        {model.enabled && (
          <div style={{ color: '#34c759', fontSize: '12px', padding: '2px 8px', backgroundColor: 'rgba(52,199,89,0.15)', borderRadius: '4px' }}>
            已启用
          </div>
        )}
      </div>

      {/* Form */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
        <div style={{ maxWidth: '480px' }}>
          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', marginBottom: '8px', color: '#a0a0a0', fontSize: '13px' }}>
              API URL
            </label>
            <input
              type="text"
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              placeholder="https://api.example.com"
              style={{
                width: '100%',
                padding: '10px 14px',
                backgroundColor: '#0f0f0f',
                border: '1px solid #333',
                borderRadius: '8px',
                color: '#e5e5e5',
                fontSize: '14px',
                boxSizing: 'border-box',
              }}
            />
          </div>

          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', marginBottom: '8px', color: '#a0a0a0', fontSize: '13px' }}>
              API Key
              {model.configured && (
                <span style={{ color: '#555', fontSize: '12px', marginLeft: '8px' }}>
                  (已配置: {model.apiKeyMasked})
                </span>
              )}
              {!model.configured && (
                <span style={{ color: '#555', fontSize: '12px', marginLeft: '8px' }}>(未配置)</span>
              )}
            </label>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={model.configured ? '输入新值以更新' : '输入 API Key'}
                style={{
                  flex: 1,
                  padding: '10px 14px',
                  backgroundColor: '#0f0f0f',
                  border: '1px solid #333',
                  borderRadius: '8px',
                  color: '#e5e5e5',
                  fontSize: '14px',
                }}
              />
              <button
                onClick={() => setShowKey(!showKey)}
                style={{
                  padding: '10px 14px',
                  backgroundColor: '#2a2a2a',
                  border: '1px solid #3a3a3a',
                  borderRadius: '8px',
                  color: '#a0a0a0',
                  fontSize: '13px',
                  cursor: 'pointer',
                  flexShrink: 0,
                }}
              >
                {showKey ? '隐藏' : '显示'}
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              onClick={onBack}
              style={{
                padding: '10px 24px',
                backgroundColor: 'transparent',
                border: '1px solid #333',
                borderRadius: '8px',
                color: '#a0a0a0',
                fontSize: '14px',
                cursor: 'pointer',
              }}
            >
              取消
            </button>
            <button
              onClick={handleSave}
              style={{
                padding: '10px 24px',
                backgroundColor: '#0066cc',
                border: 'none',
                borderRadius: '8px',
                color: '#fff',
                fontSize: '14px',
                cursor: 'pointer',
              }}
            >
              保存配置
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

interface SettingsModalProps {
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ onClose }) => {
  const { modelProviders, fetchModelProviders, setActiveModel, updateProviderConfig } = useChatStore();
  const [configuringId, setConfiguringId] = useState<string | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchModelProviders();
  }, [fetchModelProviders]);

  const handleEnable = (id: string) => {
    const provider = modelProviders.find((p) => p.id === id);
    const model = provider?.defaultModel || PROVIDER_DEFAULT_MODELS[id] || '';
    setActiveModel(id, model);
  };

  const handleConfigure = (id: string) => {
    setConfiguringId(id);
  };

  const handleSaveConfig = (id: string, apiKey: string, apiBase: string) => {
    updateProviderConfig(id, { apiKey, apiBase });
  };

  const configuredProviders = modelProviders.filter(p => p.configured);
  const unconfiguredProviders = modelProviders.filter(p => !p.configured);
  const configuringProvider = modelProviders.find(p => p.id === configuringId);

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        style={{
          width: '90vw',
          maxWidth: '1100px',
          height: '90vh',
          backgroundColor: '#1c1c1e',
          borderRadius: '12px',
          border: '1px solid #333',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* Main list view */}
        <div
          ref={gridRef}
          style={{
            width: '100%',
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            transition: 'opacity 0.2s',
            opacity: configuringId ? 0 : 1,
            pointerEvents: configuringId ? 'none' : 'auto',
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '16px 24px',
              borderBottom: '1px solid #333',
              flexShrink: 0,
            }}
          >
            <span style={{ color: '#e5e5e5', fontSize: '16px', fontWeight: 600 }}>模型配置</span>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                color: '#a0a0a0',
                fontSize: '20px',
                cursor: 'pointer',
                padding: '4px',
                lineHeight: 1,
              }}
            >
              ×
            </button>
          </div>

          {/* Content */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
            {/* Configured section */}
            {configuredProviders.length > 0 && (
              <div style={{ marginBottom: '24px' }}>
                <div style={{ color: '#666', fontSize: '12px', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '12px', paddingLeft: '4px' }}>
                  已配置
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
                    gap: '12px',
                    alignItems: 'start',
                  }}
                >
                  {configuredProviders.map((provider) => (
                    <div
                      key={provider.id}
                      style={{
                        backgroundColor: '#0f0f0f',
                        border: `1px solid ${provider.enabled ? '#34c759' : '#2a2a2a'}`,
                        borderRadius: '10px',
                        padding: '16px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '10px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div>
                          <div style={{ color: '#e5e5e5', fontSize: '14px', fontWeight: 500 }}>{provider.name}</div>
                          {provider.enabled && <div style={{ fontSize: '11px', color: '#34c759', marginTop: '2px' }}>已启用</div>}
                          {!provider.enabled && <div style={{ fontSize: '11px', color: '#555', marginTop: '2px' }}>未启用</div>}
                        </div>
                        <button
                          onClick={() => handleConfigure(provider.id)}
                          style={{
                            padding: '5px 12px',
                            backgroundColor: '#2a2a2a',
                            border: '1px solid #3a3a3a',
                            borderRadius: '6px',
                            color: '#c0c0c0',
                            fontSize: '12px',
                            cursor: 'pointer',
                          }}
                        >
                          配置
                        </button>
                      </div>
                      {provider.apiBase && (
                        <div style={{ fontSize: '11px', color: '#555', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {provider.apiBase}
                        </div>
                      )}
                      <button
                        onClick={() => handleEnable(provider.id)}
                        style={{
                          width: '100%',
                          padding: '7px 0',
                          backgroundColor: provider.enabled ? '#34c759' : '#2a2a2a',
                          border: 'none',
                          borderRadius: '6px',
                          color: '#fff',
                          fontSize: '12px',
                          cursor: 'pointer',
                        }}
                      >
                        {provider.enabled ? '已启用' : '启用'}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Unconfigured section */}
            {unconfiguredProviders.length > 0 && (
              <div>
                <div style={{ color: '#666', fontSize: '12px', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '12px', paddingLeft: '4px' }}>
                  未配置
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
                    gap: '12px',
                    alignItems: 'start',
                  }}
                >
                  {unconfiguredProviders.map((provider) => (
                    <div
                      key={provider.id}
                      style={{
                        backgroundColor: '#0f0f0f',
                        border: '1px solid #2a2a2a',
                        borderRadius: '10px',
                        padding: '16px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '10px',
                        opacity: 0.6,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div>
                          <div style={{ color: '#888', fontSize: '14px', fontWeight: 500 }}>{provider.name}</div>
                          <div style={{ fontSize: '11px', color: '#444', marginTop: '2px' }}>未配置</div>
                        </div>
                        <button
                          onClick={() => handleConfigure(provider.id)}
                          style={{
                            padding: '5px 12px',
                            backgroundColor: '#2a2a2a',
                            border: '1px solid #3a3a3a',
                            borderRadius: '6px',
                            color: '#c0c0c0',
                            fontSize: '12px',
                            cursor: 'pointer',
                          }}
                        >
                          配置
                        </button>
                      </div>
                      <button
                        disabled
                        style={{
                          width: '100%',
                          padding: '7px 0',
                          backgroundColor: '#1e1e1e',
                          border: 'none',
                          borderRadius: '6px',
                          color: '#444',
                          fontSize: '12px',
                          cursor: 'not-allowed',
                        }}
                      >
                        启用
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Config page overlay */}
        {configuringProvider && (
          <ModelConfigPage
            model={configuringProvider}
            onBack={() => setConfiguringId(null)}
            onSave={handleSaveConfig}
          />
        )}
      </div>
    </div>
  );
};