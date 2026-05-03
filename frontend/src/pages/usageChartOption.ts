import type { EChartsCoreOption } from 'echarts/core';

import type { UsageGroupBy, UsageRow } from '../types/usage';

const COLORS = {
  input: '#7896ff',
  cached: '#5cd0c0',
  cacheWrite: '#ffb95c',
  output: '#a78bfa',
} as const;

const TIME_GROUPS = new Set<UsageGroupBy>(['day', 'month', 'year']);

const baseOption = (): EChartsCoreOption => ({
  backgroundColor: 'transparent',
  textStyle: { color: 'rgba(255, 255, 255, 0.7)', fontSize: 12 },
  tooltip: {
    backgroundColor: 'rgba(20, 22, 30, 0.95)',
    borderColor: 'rgba(255, 255, 255, 0.12)',
    borderWidth: 1,
    textStyle: { color: 'rgba(255, 255, 255, 0.92)', fontSize: 12 },
  },
  legend: {
    textStyle: { color: 'rgba(255, 255, 255, 0.65)' },
    icon: 'roundRect',
    itemWidth: 10,
    itemHeight: 10,
    top: 0,
  },
});

const axisStyle = {
  axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.12)' } },
  axisTick: { lineStyle: { color: 'rgba(255, 255, 255, 0.12)' } },
  axisLabel: { color: 'rgba(255, 255, 255, 0.55)', fontSize: 11 },
  splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.06)' } },
};

function timeSeriesOption(items: UsageRow[], showCacheWrite: boolean): EChartsCoreOption {
  // Backend returns most-recent-first; charts read better LTR by date.
  const ordered = [...items].reverse();
  const buckets = ordered.map((row) => row.bucket);
  const series: object[] = [
    {
      name: '输入(未命中)',
      type: 'line',
      stack: 'tokens',
      areaStyle: { opacity: 0.55 },
      smooth: true,
      symbol: 'none',
      itemStyle: { color: COLORS.input },
      data: ordered.map((row) => row.inputTokens),
    },
    {
      name: '缓存命中',
      type: 'line',
      stack: 'tokens',
      areaStyle: { opacity: 0.55 },
      smooth: true,
      symbol: 'none',
      itemStyle: { color: COLORS.cached },
      data: ordered.map((row) => row.cachedInputTokens),
    },
  ];
  if (showCacheWrite) {
    series.push({
      name: '缓存写入',
      type: 'line',
      stack: 'tokens',
      areaStyle: { opacity: 0.55 },
      smooth: true,
      symbol: 'none',
      itemStyle: { color: COLORS.cacheWrite },
      data: ordered.map((row) => row.cacheWriteTokens),
    });
  }
  series.push({
    name: '输出',
    type: 'line',
    stack: 'tokens',
    areaStyle: { opacity: 0.55 },
    smooth: true,
    symbol: 'none',
    itemStyle: { color: COLORS.output },
    data: ordered.map((row) => row.outputTokens),
  });

  return {
    ...baseOption(),
    grid: { left: 50, right: 16, top: 36, bottom: 28 },
    tooltip: { ...(baseOption().tooltip as object), trigger: 'axis' },
    xAxis: { type: 'category', data: buckets, ...axisStyle },
    yAxis: { type: 'value', ...axisStyle },
    series,
  };
}

function categoricalBarOption(
  items: UsageRow[],
  showCacheWrite: boolean,
): EChartsCoreOption {
  // Top-N already sorted DESC by backend; reverse for ECharts horizontal bar
  // (which renders the first item at the bottom).
  const ordered = [...items].slice(0, 12).reverse();
  const buckets = ordered.map((row) => row.bucket);

  const series: object[] = [
    {
      name: '输入(未命中)',
      type: 'bar',
      stack: 'tokens',
      itemStyle: { color: COLORS.input, borderRadius: [0, 0, 0, 0] },
      data: ordered.map((row) => row.inputTokens),
    },
    {
      name: '缓存命中',
      type: 'bar',
      stack: 'tokens',
      itemStyle: { color: COLORS.cached },
      data: ordered.map((row) => row.cachedInputTokens),
    },
  ];
  if (showCacheWrite) {
    series.push({
      name: '缓存写入',
      type: 'bar',
      stack: 'tokens',
      itemStyle: { color: COLORS.cacheWrite },
      data: ordered.map((row) => row.cacheWriteTokens),
    });
  }
  series.push({
    name: '输出',
    type: 'bar',
    stack: 'tokens',
    itemStyle: { color: COLORS.output, borderRadius: [0, 4, 4, 0] },
    data: ordered.map((row) => row.outputTokens),
  });

  return {
    ...baseOption(),
    grid: { left: 140, right: 24, top: 36, bottom: 16 },
    tooltip: { ...(baseOption().tooltip as object), trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', ...axisStyle },
    yAxis: {
      type: 'category',
      data: buckets,
      ...axisStyle,
      axisLabel: { ...axisStyle.axisLabel, formatter: (val: string) => truncate(val, 18) },
    },
    series,
  };
}

function treemapOption(items: UsageRow[]): EChartsCoreOption {
  // Color scale: deeper indigo = higher cache hit rate (more savings).
  const palette = ['#3a4a8a', '#4d63a8', '#6a82c8', '#8aa1de', '#a8b8e8'];
  const data = items.map((row, idx) => {
    const billable = row.inputTokens + row.cachedInputTokens;
    const hitRate = billable === 0 ? 0 : row.cachedInputTokens / billable;
    return {
      name: row.bucket,
      value: row.totalTokens,
      itemStyle: { color: palette[idx % palette.length] },
      _hitRate: hitRate,
    };
  });
  return {
    ...baseOption(),
    legend: { show: false },
    tooltip: {
      ...(baseOption().tooltip as object),
      formatter: (params: { name: string; value: number; data: { _hitRate: number } }) =>
        `<strong>${params.name}</strong><br/>` +
        `总 token: ${params.value.toLocaleString()}<br/>` +
        `缓存命中率: ${(params.data._hitRate * 100).toFixed(1)}%`,
    },
    series: [
      {
        type: 'treemap',
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        data,
        label: {
          show: true,
          color: 'rgba(255, 255, 255, 0.95)',
          fontSize: 12,
          formatter: (params: { name: string; value: number }) => {
            const tokens =
              params.value < 1000
                ? params.value.toString()
                : params.value < 1_000_000
                  ? `${(params.value / 1000).toFixed(1)}k`
                  : `${(params.value / 1_000_000).toFixed(2)}M`;
            return `{name|${params.name}}\n{val|${tokens}}`;
          },
          rich: {
            name: { fontSize: 12, color: 'rgba(255, 255, 255, 0.95)', lineHeight: 18 },
            val: { fontSize: 14, color: 'rgba(255, 255, 255, 0.7)', fontWeight: 600 },
          },
        },
        itemStyle: {
          borderColor: 'rgba(20, 22, 30, 0.95)',
          borderWidth: 2,
          gapWidth: 2,
        },
      },
    ],
  };
}

function pieOption(items: UsageRow[]): EChartsCoreOption {
  const data = items.map((row) => ({
    name: row.bucket,
    value: row.totalTokens,
  }));
  return {
    ...baseOption(),
    tooltip: { ...(baseOption().tooltip as object), trigger: 'item' },
    legend: { ...(baseOption().legend as object), top: 'center', left: '55%', orient: 'vertical' },
    series: [
      {
        name: '总 token',
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['28%', '50%'],
        label: { color: 'rgba(255, 255, 255, 0.85)', formatter: '{b}\n{d}%' },
        labelLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.3)' } },
        data,
      },
    ],
    color: ['#7896ff', '#5cd0c0', '#ffb95c', '#a78bfa', '#ff8b8b', '#7be0a8', '#ffd166'],
  };
}

function truncate(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, max - 1)}…`;
}

export function buildUsageChartOption(
  groupBy: UsageGroupBy,
  items: UsageRow[],
  options: { showCacheWrite: boolean },
): EChartsCoreOption {
  if (items.length === 0) {
    return { ...baseOption(), series: [] };
  }
  if (TIME_GROUPS.has(groupBy)) {
    return timeSeriesOption(items, options.showCacheWrite);
  }
  if (groupBy === 'provider') {
    return pieOption(items);
  }
  if (groupBy === 'model') {
    return treemapOption(items);
  }
  return categoricalBarOption(items, options.showCacheWrite);
}
