interface SessionRestoreStateOptions {
  currentSession: string | null;
  sessionCount: number;
  mainView:
    | 'chat'
    | 'knowledge'
    | 'assets'
    | 'browser'
    | 'project-list'
    | 'project-home'
    | 'project-chat'
    | 'settings'
    | 'tasks'
    | 'usage';
  activeProjectId: string | null;
}

export function shouldRestoreLastSession(options: SessionRestoreStateOptions): boolean {
  if (options.currentSession || options.sessionCount === 0) {
    return false;
  }

  if (options.activeProjectId) {
    return false;
  }

  return options.mainView === 'chat' || options.mainView === 'knowledge';
}
