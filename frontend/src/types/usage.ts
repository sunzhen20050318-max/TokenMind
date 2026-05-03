export type UsageGroupBy = 'day' | 'month' | 'year' | 'model' | 'session' | 'provider';

export interface UsageRow {
  bucket: string;
  inputTokens: number;
  cachedInputTokens: number;
  cacheWriteTokens: number;
  outputTokens: number;
  reasoningTokens: number;
  totalTokens: number;
  callCount: number;
}

export interface UsageAggregateResponse {
  groupBy: UsageGroupBy;
  items: UsageRow[];
  summary: UsageRow;
}

export interface UsageQuery {
  groupBy: UsageGroupBy;
  start?: string;
  end?: string;
  provider?: string;
  model?: string;
  sessionId?: string;
  limit?: number;
}
