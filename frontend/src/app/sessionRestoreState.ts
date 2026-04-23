interface SessionRestoreStateOptions {
  appReady: boolean;
  currentSession: string | null;
  sessionCount: number;
  mainView: 'chat' | 'knowledge' | 'music' | 'voice-clone' | 'video' | 'project-home' | 'project-chat';
  activeProjectId: string | null;
}

export function shouldRestoreLastSession(options: SessionRestoreStateOptions): boolean {
  if (!options.appReady || options.currentSession || options.sessionCount === 0) {
    return false;
  }

  if (options.activeProjectId) {
    return false;
  }

  return options.mainView === 'chat' || options.mainView === 'knowledge';
}
