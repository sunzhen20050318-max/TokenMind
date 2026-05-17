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

const CATEGORY_COLORS: Record<string, string> = {
  entity: '#a6c4ff',
  topic: '#b3d8b1',
  source: '#d9c98a',
  synthesis: '#e0a6ff',
  comparison: '#ffb38a',
  query: '#cccccc',
  page: '#888888',
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
    if (!containerRef.current) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(containerRef.current, 'dark');
    }
    const onClick = (params: unknown) => {
      const p = params as { dataType?: string; data?: { path?: string } | null };
      const path = p?.data && typeof p.data === 'object' ? p.data.path : undefined;
      if (p?.dataType === 'node' && path && onSelectNode) {
        onSelectNode(path);
      }
    };
    chartRef.current.on('click', onClick);
    return () => {
      chartRef.current?.off('click', onClick);
    };
  }, [onSelectNode]);

  useEffect(() => {
    if (!chartRef.current || !data) return;
    const categories = Array.from(new Set(data.nodes.map((n) => n.type))).map((t) => ({ name: t }));
    chartRef.current.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        formatter: (params: { dataType?: string; data?: { name?: string; type?: string; summary?: string } }) => {
          if (params.dataType !== 'node') return '';
          const d = params.data ?? {};
          return `<strong>${d.name ?? ''}</strong><br/>${d.type ?? ''}<br/>${d.summary ?? ''}`;
        },
      },
      legend: {
        data: categories.map((c) => c.name),
        textStyle: { color: '#b6b6bf', fontSize: 11 },
        top: 8,
      },
      series: [
        {
          type: 'graph',
          layout: 'force',
          force: { repulsion: 220, gravity: 0.05, edgeLength: [60, 140] },
          roam: true,
          draggable: true,
          label: { show: true, position: 'right', color: '#f5f5f7', fontSize: 11 },
          lineStyle: { color: 'rgba(255,255,255,0.18)', width: 1 },
          emphasis: { focus: 'adjacency', lineStyle: { width: 2 } },
          categories,
          data: data.nodes.map((n) => ({
            id: n.id,
            name: n.title,
            type: n.type,
            path: n.path,
            summary: n.summary,
            category: n.type,
            symbolSize: 8 + Math.min(n.degree * 3, 24),
            itemStyle: { color: CATEGORY_COLORS[n.type] ?? '#888888' },
          })),
          links: data.edges.map((e) => ({ source: e.source, target: e.target })),
        },
      ],
    });
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
