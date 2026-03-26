export interface CronJobState {
  next_run_at_ms: number | null;
  last_run_at_ms: number | null;
  last_status: string | null;
  last_error: string | null;
}

export interface CronJobSchedule {
  kind: 'every' | 'cron' | 'at';
  every_ms: number | null;
  expr: string | null;
  tz: string | null;
  at_ms: number | null;
  label: string;
}

export interface CronJob {
  id: string;
  name: string;
  enabled: boolean;
  message: string;
  deliver: boolean;
  channel: string | null;
  to: string | null;
  schedule: CronJobSchedule;
  state: CronJobState;
  created_at_ms: number;
  updated_at_ms: number;
  delete_after_run: boolean;
}

export interface CronStatus {
  enabled: boolean;
  jobs: number;
  next_wake_at_ms: number | null;
}

export interface CreateCronJobPayload {
  name: string;
  message: string;
  schedule_kind: 'every' | 'cron' | 'at';
  every_seconds?: number;
  cron_expr?: string;
  tz?: string;
  at?: string;
  deliver: boolean;
  session_id?: string | null;
}
