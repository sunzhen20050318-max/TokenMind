import { useCallback, useEffect, useMemo, useState } from 'react';

import { EChart } from '../components/charts/EChart';
import { api } from '../services/api';
import type { UsageAggregateResponse, UsageQuery, UsageRow } from '../types/usage';
import { buildUsageChartOption } from './usageChartOption';
import './usage.css';

const RANGE_PRESETS = [
  { value: '7d', label: '近 7 天' },
  { value: '30d', label: '近 30 天' },
  { value: '90d', label: '近 90 天' },
  { value: 'all', label: '全部' },
  { value: 'custom', label: '自定义' },
] as const;

type RangePreset = (typeof RANGE_PRESETS)[number]['value'];

interface FilterState {
  range: RangePreset;
  customStart: string; // YYYY-MM-DD, only used when range === 'custom'
  customEnd: string;
  model: string; // '' means all
  sessionId: string;
  provider: string;
}

interface ChartBundle {
  trend: UsageAggregateResponse;
  byModel: UsageAggregateResponse;
  bySession: UsageAggregateResponse;
  byProvider: UsageAggregateResponse;
}

interface FilterOptions {
  models: string[];
  sessions: string[];
  providers: string[];
}

const INITIAL_FILTERS: FilterState = {
  range: '30d',
  customStart: '',
  customEnd: '',
  model: '',
  sessionId: '',
  provider: '',
};

function formatTokens(value: number): string {
  if (value < 1_000) return value.toLocaleString();
  if (value < 1_000_000) return `${(value / 1_000).toFixed(1)}k`;
  return `${(value / 1_000_000).toFixed(2)}M`;
}

function cacheHitRate(row: UsageRow): number {
  const billable = row.inputTokens + row.cachedInputTokens;
  return billable === 0 ? 0 : row.cachedInputTokens / billable;
}

function rangeToISO(filter: FilterState): { start?: string; end?: string } {
  if (filter.range === 'all') return {};
  if (filter.range === 'custom') {
    const out: { start?: string; end?: string } = {};
    if (filter.customStart) out.start = `${filter.customStart}T00:00:00Z`;
    if (filter.customEnd) {
      // End is exclusive in the backend; bump to next day so the picked
      // end-date is included in the result set.
      const next = new Date(`${filter.customEnd}T00:00:00Z`);
      next.setUTCDate(next.getUTCDate() + 1);
      out.end = next.toISOString();
    }
    return out;
  }
  const days = filter.range === '7d' ? 7 : filter.range === '30d' ? 30 : 90;
  const start = new Date(Date.now() - days * 86_400_000);
  return { start: start.toISOString() };
}

function filtersToQuery(filter: FilterState): Pick<UsageQuery, 'start' | 'end' | 'model' | 'sessionId' | 'provider'> {
  const q: Pick<UsageQuery, 'start' | 'end' | 'model' | 'sessionId' | 'provider'> = {
    ...rangeToISO(filter),
  };
  if (filter.model) q.model = filter.model;
  if (filter.sessionId) q.sessionId = filter.sessionId;
  if (filter.provider) q.provider = filter.provider;
  return q;
}

export function UsagePage() {
  const [filters, setFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [bundle, setBundle] = useState<ChartBundle | null>(null);
  const [options, setOptions] = useState<FilterOptions>({
    models: [],
    sessions: [],
    providers: [],
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Populate dropdowns from the entire history once. Re-fetching on every
  // filter change would shrink the dropdown to whatever survived the filter,
  // which prevents the user from broadening their selection.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [models, sessions, providers] = await Promise.all([
          api.getUsageAggregate({ groupBy: 'model', limit: 200 }),
          api.getUsageAggregate({ groupBy: 'session', limit: 100 }),
          api.getUsageAggregate({ groupBy: 'provider', limit: 50 }),
        ]);
        if (cancelled) return;
        setOptions({
          models: models.items.map((row) => row.bucket),
          sessions: sessions.items.map((row) => row.bucket),
          providers: providers.items.map((row) => row.bucket),
        });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载失败');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const baseQuery = filtersToQuery(filters);
      const [trend, byModel, bySession, byProvider] = await Promise.all([
        api.getUsageAggregate({ ...baseQuery, groupBy: 'day', limit: 365 }),
        api.getUsageAggregate({ ...baseQuery, groupBy: 'model', limit: 20 }),
        api.getUsageAggregate({ ...baseQuery, groupBy: 'session', limit: 12 }),
        api.getUsageAggregate({ ...baseQuery, groupBy: 'provider', limit: 20 }),
      ]);
      setBundle({ trend, byModel, bySession, byProvider });
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
      setBundle(null);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  const summary = bundle?.trend.summary;
  const summaryHitRate = summary ? cacheHitRate(summary) : 0;
  const showCacheWrite = (summary?.cacheWriteTokens ?? 0) > 0;
  const showReasoning = (summary?.reasoningTokens ?? 0) > 0;

  const chartOptions = useMemo(() => {
    if (!bundle) return null;
    return {
      trend: buildUsageChartOption('day', bundle.trend.items, { showCacheWrite }),
      byModel: buildUsageChartOption('model', bundle.byModel.items, { showCacheWrite }),
      bySession: buildUsageChartOption('session', bundle.bySession.items, {
        showCacheWrite,
      }),
      byProvider: buildUsageChartOption('provider', bundle.byProvider.items, {
        showCacheWrite,
      }),
    };
  }, [bundle, showCacheWrite]);

  const updateFilter = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const hasData = bundle !== null && bundle.trend.items.length > 0;

  return (
    <div className="usage-page">
      <header className="usage-page__header">
        <h1>Token 用量</h1>
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
        <FilterDropdown
          label="模型"
          value={filters.model}
          values={options.models}
          onChange={(value) => updateFilter('model', value)}
        />
        <FilterDropdown
          label="厂商"
          value={filters.provider}
          values={options.providers}
          onChange={(value) => updateFilter('provider', value)}
        />
        <FilterDropdown
          label="会话"
          value={filters.sessionId}
          values={options.sessions}
          onChange={(value) => updateFilter('sessionId', value)}
        />
        <div className="usage-page__filter-group">
          <span className="usage-page__filter-label">时间范围</span>
          <div className="usage-page__segmented">
            {RANGE_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                className={`usage-page__segment ${
                  filters.range === preset.value ? 'is-active' : ''
                }`}
                onClick={() => updateFilter('range', preset.value)}
              >
                {preset.label}
              </button>
            ))}
          </div>
          {filters.range === 'custom' ? (
            <div className="usage-page__date-range">
              <input
                type="date"
                value={filters.customStart}
                max={filters.customEnd || undefined}
                onChange={(e) => updateFilter('customStart', e.target.value)}
              />
              <span className="usage-page__date-sep">至</span>
              <input
                type="date"
                value={filters.customEnd}
                min={filters.customStart || undefined}
                onChange={(e) => updateFilter('customEnd', e.target.value)}
              />
            </div>
          ) : null}
        </div>
      </section>

      {error ? <div className="usage-page__error">{error}</div> : null}

      {summary ? (
        <section className="usage-page__summary">
          <SummaryCard label="总 token" value={summary.totalTokens} highlight />
          <SummaryCard label="输入(未命中)" value={summary.inputTokens} />
          <SummaryCard label="缓存命中" value={summary.cachedInputTokens} />
          {showCacheWrite ? (
            <SummaryCard label="缓存写入" value={summary.cacheWriteTokens} />
          ) : null}
          <SummaryCard label="输出" value={summary.outputTokens} />
          {showReasoning ? (
            <SummaryCard label="推理(含于输出)" value={summary.reasoningTokens} muted />
          ) : null}
          <SummaryCard
            label="缓存命中率"
            text={`${(summaryHitRate * 100).toFixed(1)}%`}
          />
          <SummaryCard label="调用次数" value={summary.callCount} />
        </section>
      ) : null}

      {hasData && chartOptions ? (
        <>
          <ChartCard title="使用趋势" subtitle="按天聚合,堆叠展示输入、缓存、输出">
            <EChart option={chartOptions.trend} height={320} />
          </ChartCard>

          <div className="usage-page__chart-row">
            <ChartCard title="按模型" subtitle="矩形面积代表累计 token,鼠标悬停查看缓存命中率">
              <EChart option={chartOptions.byModel} height={320} />
            </ChartCard>
            <ChartCard title="按厂商" subtitle="累计 token 占比">
              <EChart option={chartOptions.byProvider} height={320} />
            </ChartCard>
          </div>

          <ChartCard title="Top 会话" subtitle="累计 token 最高的 12 个会话">
            <EChart option={chartOptions.bySession} height={360} />
          </ChartCard>
        </>
      ) : (
        <div className="usage-page__empty">
          {loading ? '加载中…' : '当前筛选范围内没有数据'}
        </div>
      )}
    </div>
  );
}

interface FilterDropdownProps {
  label: string;
  value: string;
  values: string[];
  onChange: (value: string) => void;
}

function FilterDropdown({ label, value, values, onChange }: FilterDropdownProps) {
  return (
    <div className="usage-page__filter-group">
      <span className="usage-page__filter-label">{label}</span>
      <select
        className="usage-page__select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">全部</option>
        {values.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

interface ChartCardProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

function ChartCard({ title, subtitle, children }: ChartCardProps) {
  return (
    <section className="usage-page__chart">
      <header className="usage-page__chart-head">
        <h2>{title}</h2>
        {subtitle ? <span>{subtitle}</span> : null}
      </header>
      {children}
    </section>
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
