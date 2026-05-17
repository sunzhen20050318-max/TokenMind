import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts/core';
import { GraphChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import { api } from '../../services/api';
import type { WikiGraphData } from '../../types/knowledge';
import './knowledgeGraph.css';

echarts.use([GraphChart, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

interface KnowledgeGraphProps {
  knowledgeBaseId: string;
  onSelectNode?: (path: string) => void;
}

// Muted palette inspired by Obsidian's graph: low-saturation,
// single-direction hue per page type, kept readable on dark background.
const CATEGORY_COLORS: Record<string, string> = {
  entity: '#7a9cd9',
  topic: '#7fb37d',
  source: '#c0a86b',
  synthesis: '#b07ed9',
  comparison: '#d99a6b',
  query: '#888888',
  page: '#6e6e6e',
};

export const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ knowledgeBaseId, onSelectNode }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [data, setData] = useState<WikiGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rebuilding, setRebuilding] = useState(false);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.getWikiGraph(knowledgeBaseId));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载图谱失败');
    } finally {
      setLoading(false);
    }
  }, [knowledgeBaseId]);

  const handleRebuild = useCallback(async () => {
    setRebuilding(true);
    setError(null);
    try {
      setData(await api.rebuildWikiGraph(knowledgeBaseId));
    } catch (err) {
      setError(err instanceof Error ? err.message : '重建图谱失败');
    } finally {
      setRebuilding(false);
    }
  }, [knowledgeBaseId]);

  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(container, 'dark');
    }
    const onClick = (params: unknown) => {
      const p = params as { dataType?: string; data?: { path?: string } | null };
      const path = p?.data && typeof p.data === 'object' ? p.data.path : undefined;
      if (p?.dataType === 'node' && path && onSelectNode) {
        onSelectNode(path);
      }
    };
    chartRef.current.on('click', onClick);

    const ro = new ResizeObserver(() => {
      chartRef.current?.resize();
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chartRef.current?.off('click', onClick);
    };
  }, [onSelectNode]);

  useEffect(() => {
    if (!chartRef.current || !data) return;
    const categories = Array.from(new Set(data.nodes.map((n) => n.type))).map((t) => ({ name: t }));
    chartRef.current.setOption(
      {
        backgroundColor: 'transparent',
        tooltip: {
          backgroundColor: 'rgba(20,20,22,0.94)',
          borderColor: 'rgba(255,255,255,0.12)',
          textStyle: { color: '#e5e5e5', fontSize: 12 },
          formatter: (params: { dataType?: string; data?: { name?: string; type?: string; summary?: string } }) => {
            if (params.dataType !== 'node') return '';
            const d = params.data ?? {};
            const summary = d.summary?.trim();
            return `<strong>${d.name ?? ''}</strong><div style="opacity:0.6;font-size:11px;margin-top:2px">${d.type ?? ''}</div>${summary ? `<div style="margin-top:6px;max-width:280px;line-height:1.5">${summary}</div>` : ''}`;
          },
        },
        legend: {
          data: categories.map((c) => c.name),
          textStyle: { color: '#888', fontSize: 11 },
          itemWidth: 8,
          itemHeight: 8,
          top: 10,
          right: 16,
          orient: 'horizontal',
        },
        series: [
          {
            type: 'graph',
            layout: 'force',
            force: {
              repulsion: 320,
              gravity: 0.08,
              edgeLength: [80, 180],
              friction: 0.15,
            },
            roam: true,
            draggable: true,
            zoom: 1.0,
            label: {
              show: true,
              position: 'right',
              color: '#9a9aa3',
              fontSize: 11,
              formatter: '{b}',
            },
            lineStyle: {
              color: 'rgba(255,255,255,0.10)',
              width: 0.8,
              curveness: 0,
            },
            emphasis: {
              focus: 'adjacency',
              scale: 1.1,
              label: { color: '#ffffff', fontSize: 12 },
              lineStyle: { color: 'rgba(166,196,255,0.55)', width: 1.5 },
            },
            blur: {
              itemStyle: { opacity: 0.18 },
              lineStyle: { opacity: 0.05 },
              label: { opacity: 0.2 },
            },
            categories,
            data: data.nodes.map((n) => ({
              id: n.id,
              name: n.title,
              type: n.type,
              path: n.path,
              summary: n.summary,
              category: n.type,
              symbolSize: 6 + Math.min(n.degree * 2.5, 22),
              itemStyle: {
                color: CATEGORY_COLORS[n.type] ?? '#888888',
                borderColor: 'rgba(255,255,255,0.18)',
                borderWidth: 0.5,
                opacity: 0.92,
              },
            })),
            links: data.edges.map((e) => ({ source: e.source, target: e.target })),
          },
        ],
      },
      { notMerge: true },
    );
    chartRef.current.resize();
  }, [data]);

  useEffect(() => {
    const onResize = () => chartRef.current?.resize();
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  return (
    <div className="kb-graph">
      <div className="kb-graph__toolbar">
        <span className="kb-graph__stats">
          {data ? `${data.nodes.length} 节点 · ${data.edges.length} 边` : ''}
        </span>
        <button
          type="button"
          className="kb-graph__button"
          onClick={() => void handleRebuild()}
          disabled={rebuilding || loading}
        >
          {rebuilding ? '重建中…' : '重建图谱'}
        </button>
      </div>
      {loading && <div className="kb-graph__placeholder">加载中…</div>}
      {error && <div className="kb-graph__placeholder is-error">{error}</div>}
      <div ref={containerRef} className="kb-graph__canvas" />
    </div>
  );
};
