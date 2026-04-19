import type { Session } from '../../types';

interface BuildProjectEntryStateOptions {
  projectName: string;
  sessions: Session[];
}

const EMPTY_HINT =
  '\u8fd8\u6ca1\u6709\u9879\u76ee\u804a\u5929\uff0c\u76f4\u63a5\u5728\u4e0a\u9762\u7684\u8f93\u5165\u6846\u91cc\u53d1\u8d77\u7b2c\u4e00\u6bb5\u9879\u76ee\u5185\u5bf9\u8bdd\u3002';

export function buildProjectEntryState(options: BuildProjectEntryStateOptions) {
  return {
    title: options.projectName,
    showEmptyHint: options.sessions.length === 0,
    emptyHint: EMPTY_HINT,
  };
}
