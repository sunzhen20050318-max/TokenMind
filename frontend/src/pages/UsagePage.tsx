import { useCallback, useEffect, useMemo, useState } from 'react';

import { api } from '../services/api';
import type { UsageAggregateResponse, UsageGroupBy, UsageRow } from '../types/usage';
import './usage.css';

const GROUP_OPTIONS: { value: UsageGroupBy; label: string }[] = [
  { value: 'day', label: '按天' },
  { value: 'month', label: '按月' },
  { value: 'year', label: '按年' },
  { value: 'model', label: '按模型' },
  { value: 'session', label: '按会话' },
  { value: 'provider', label: '按厂商' },
];

const RANGE_PRESETS = [
  { value: '7d', label: '近 7 天' },
  { value: '30d', label: '近 30 天' },
  { value: '90d', label: '近 90 天' },
  { value: 'all', label: '全部' },
] as const;

type RangePreset = (typeof RANGE_PRESETS)[number]['value'];

function formatTokens(value: number): string {
  if (value < 1_000) return value.toLocaleString();
  if (value < 1_000_000) return `${(value / 1_000).toFixed(1)}k`;
  return `${(value / 1_000_000).toFixed(2)}M`;
}

function cacheHitRate(row: UsageRow): number {
  const billable = row.inputTokens + row.cachedInputTokens;
  return billable === 0 ? 0 : row.cachedInputTokens / billable;
}

function rangeToISO(preset: RangePreset): { start?: string; end?: string } {
  if (preset === 'all') return {};
  const days = preset === '7d' ? 7 : preset === '30d' ? 30 : 90;
  const start = new Date(Date.now() - days * 86_400_000);
  return { start: start.toISOString() };
}

export function UsagePage() {
  const [groupBy, setGroupBy] = useState<UsageGroupBy>('day');
  const [range, setRange] = useState<RangePreset>('30d');
  const [data, setData] = useState<UsageAggregateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getUsageAggregate({
        groupBy,
        ...rangeToISO(range),
        limit: 200,
      });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [groupBy, range]);

  useEffect(() => {
    void load();
  }, [load]);

  const maxTotal = useMemo(() => {
    if (!data || data.items.length === 0) return 0;
    return Math.max(...data.items.map((row) => row.totalTokens));
  }, [data]);

  const summary = data?.summary;
  const summaryHitRate = summary ? cacheHitRate(summary) : 0;

  return (
    <div className="usage-page">
      <header className="usage-page__header">
        <div>
          <h1>Token 用量</h1>
          <p className="usage-page__subtitle">
            统计每次 LLM 调用的输入、输出、缓存命中与推理 token,按多维度聚合。
          </p>
        </div>
        <button
          type="button"
          className="usage-page__refresh"
          onClick={() => {
            void load();
          }}
          disabled={loading}
        >
          {loading ? '加载中…' : '刷新'}
        </button>
      </header>

      <section className="usage-page__filters">
        <div className="usage-page__filter-group">
          <span className="usage-page__filter-label">维度</span>
          <div className="usage-page__segmented">
            {GROUP_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`usage-page__segment ${
                  groupBy === option.value ? 'is-active' : ''
                }`}
                onClick={() => setGroupBy(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="usage-page__filter-group">
          <span className="usage-page__filter-label">时间范围</span>
          <div className="usage-page__segmented">
            {RANGE_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                className={`usage-page__segment ${
                  range === preset.value ? 'is-active' : ''
                }`}
                onClick={() => setRange(preset.value)}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {error ? <div className="usage-page__error">{error}</div> : null}

      {summary ? (
        <section className="usage-page__summary">
          <SummaryCard label="总 token" value={summary.totalTokens} highlight />
          <SummaryCard label="输入(未命中)" value={summary.inputTokens} />
          <SummaryCard label="缓存命中" value={summary.cachedInputTokens} />
          <SummaryCard label="缓存写入" value={summary.cacheWriteTokens} />
          <SummaryCard label="输出" value={summary.outputTokens} />
          <SummaryCard label="推理(含于输出)" value={summary.reasoningTokens} muted />
          <SummaryCard
            label="缓存命中率"
            text={`${(summaryHitRate * 100).toFixed(1)}%`}
          />
          <SummaryCard label="调用次数" value={summary.callCount} />
        </section>
      ) : null}

      <section className="usage-page__table">
        <div className="usage-page__table-head">
          <span className="usage-page__col-bucket">{bucketLabel(groupBy)}</span>
          <span>输入</span>
          <span>缓存命中</span>
          <span>缓存写入</span>
          <span>输出</span>
          <span>推理</span>
          <span>合计</span>
          <span>调用</span>
        </div>

        {data && data.items.length > 0 ? (
          data.items.map((row) => (
            <div key={row.bucket} className="usage-page__row">
              <span className="usage-page__col-bucket" title={row.bucket}>
                {row.bucket}
              </span>
              <span>{formatTokens(row.inputTokens)}</span>
              <span>{formatTokens(row.cachedInputTokens)}</span>
              <span>{formatTokens(row.cacheWriteTokens)}</span>
              <span>{formatTokens(row.outputTokens)}</span>
              <span className="usage-page__cell-muted">
                {row.reasoningTokens > 0 ? formatTokens(row.reasoningTokens) : '—'}
              </span>
              <span className="usage-page__cell-total">
                <span
                  className="usage-page__bar"
                  style={{
                    width:
                      maxTotal > 0
                        ? `${(row.totalTokens / maxTotal) * 100}%`
                        : '0%',
                  }}
                />
                <span>{formatTokens(row.totalTokens)}</span>
              </span>
              <span>{row.callCount}</span>
            </div>
          ))
        ) : (
          <div className="usage-page__empty">
            {loading ? '加载中…' : '当前范围内没有数据'}
          </div>
        )}
      </section>
    </div>
  );
}

interface SummaryCardProps {
  label: string;
  value?: number;
  text?: string;
  highlight?: boolean;
  muted?: boolean;
}

function SummaryCard({ label, value, text, highlight, muted }: SummaryCardProps) {
  const display = text ?? (typeof value === 'number' ? formatTokens(value) : '—');
  const className = [
    'usage-page__summary-card',
    highlight ? 'is-highlight' : '',
    muted ? 'is-muted' : '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <div className={className}>
      <span className="usage-page__summary-label">{label}</span>
      <span className="usage-page__summary-value">{display}</span>
    </div>
  );
}

function bucketLabel(groupBy: UsageGroupBy): string {
  switch (groupBy) {
    case 'day':
      return '日期';
    case 'month':
      return '月份';
    case 'year':
      return '年份';
    case 'model':
      return '模型';
    case 'session':
      return '会话';
    case 'provider':
      return '厂商';
  }
}
