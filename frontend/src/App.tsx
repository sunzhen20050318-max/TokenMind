import React, { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { shouldRestoreLastSession } from './app/sessionRestoreState';
import { AttachmentPreview } from './components/AttachmentPreview/AttachmentPreview';
import { CrossSessionApprovalToast } from './components/CrossSessionToast/CrossSessionApprovalToast';
import { Header } from './components/Layout/Header';
import { AnnouncementToast } from './components/Updates/AnnouncementToast';
import { UpdateModal } from './components/Updates/UpdateModal';
import { Sidebar } from './components/Layout/Sidebar';
import { ChatWindow } from './components/Chat/ChatWindow';
import { createProjectConversation } from './components/Projects/projectEntryFlow';
import { BrowserPage } from './pages/Browser';
import { KnowledgePage } from './pages/Knowledge';
import { AssetsPage } from './pages/Assets';
import { ProjectHome } from './pages/ProjectHome';
import { ProjectsGrid } from './pages/ProjectsGrid';
import { SettingsPage } from './pages/Settings';
import type { SectionId } from './pages/Settings';
// UsagePage pulls in ECharts (~190kB gz). Lazy-load so the main bundle stays
// slim for users who never open the usage view.
const UsagePage = lazy(() =>
  import('./pages/UsagePage').then((module) => ({ default: module.UsagePage })),
);
import { api } from './services/api';
import {
  compareVersions,
  fetchVersionInfo,
  POLL_INTERVAL_MS,
  setPendingSkillSuggestions,
} from './services/updates';
import type { VersionInfo } from './types/updates';
import { StaleClientBanner } from './components/Updates/StaleClientBanner';
import { ToastContainer } from './components/Toast/ToastContainer';
import { CommandPalette } from './components/CommandPalette/CommandPalette';
import type { CommandPaletteAction } from './components/CommandPalette/CommandPalette';
import { useChatStore } from './stores/chatStore';
import { useToastStore } from './stores/toastStore';
import { useSessions } from './hooks/useSessions';
import { useSessionOrchestrator } from './hooks/useSessionOrchestrator';
import { APP_VERSION } from './version';
import './app.css';

const LAST_SESSION_KEY = 'tokenmind:last-session';
const SIDEBAR_COLLAPSED_KEY = 'tokenmind:sidebar-collapsed';
// One-shot guard so the version-mismatch reload below can't loop. Cleared
// when the tab closes (sessionStorage scope is intentional — a stale cache
// re-appearing in a future tab session deserves another reload).
const VERSION_RELOAD_GUARD_KEY = 'tokenmind:version-reload-done';

const App: React.FC = () => {
  // Mount the WebSocket orchestrator at the app root so the chat WS lifecycle
  // is independent of the ChatWindow component (which gets unmounted whenever
  // the user navigates to settings, asset library, music studio, etc.).
  useSessionOrchestrator();

  // Reconcile a stale browser cache after an in-place upgrade. The bundled
  // APP_VERSION is a compile-time constant — if it doesn't match what the
  // backend reports (the actual installed package version), this tab is
  // running JS from a previous install. One hard reload + a sessionStorage
  // guard against loops fixes it; the no-cache headers on index.html make
  // sure the reload picks up the fresh bundle.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (sessionStorage.getItem(VERSION_RELOAD_GUARD_KEY)) return;
    let cancelled = false;
    (async () => {
      try {
        const status = await api.getStatus();
        if (cancelled || !status?.version) return;
        // Only reload when the backend is genuinely newer than the bundled
        // JS — the inverse (backend older than this tab) happens when a dev
        // has rebuilt the frontend without reinstalling the Python package,
        // and force-reloading there would just lose work for nothing.
        if (compareVersions(APP_VERSION, status.version) < 0) {
          sessionStorage.setItem(VERSION_RELOAD_GUARD_KEY, '1');
          window.location.reload();
        }
      } catch {
        // Network blip — re-check on next reload.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Long-lived sessions (tab never closed) miss the mount-time check above
  // because it only fires once. Poll /api/status every 5 minutes; if the
  // server has been upgraded under us, surface a non-intrusive banner —
  // explicitly NOT auto-reload, because that would wipe whatever the user
  // is in the middle of typing/uploading/streaming.
  const [staleServerVersion, setStaleServerVersion] = useState<string | null>(null);
  const [staleBannerDismissed, setStaleBannerDismissed] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    let cancelled = false;
    const checkServerVersion = async () => {
      try {
        const status = await api.getStatus();
        if (cancelled || !status?.version) return;
        // Only show the stale-tab banner when the server is genuinely newer
        // than this tab. The reverse (server older than the bundled JS)
        // happens during local development when the frontend has been
        // rebuilt without reinstalling the Python package — showing a "new
        // version available" hint there would be misleading and the
        // version number on the banner would be the *older* of the two.
        if (compareVersions(APP_VERSION, status.version) < 0) {
          setStaleServerVersion(status.version);
        }
      } catch {
        // Ignore — periodic check, no need to surface transient failures.
      }
    };
    // First periodic check 30s after load (mount-time check has already run);
    // then every 5 minutes thereafter.
    const initialTid = window.setTimeout(() => void checkServerVersion(), 30_000);
    const intervalTid = window.setInterval(
      () => void checkServerVersion(),
      5 * 60 * 1000,
    );
    return () => {
      cancelled = true;
      window.clearTimeout(initialTid);
      window.clearInterval(intervalTid);
    };
  }, []);

  const showStaleBanner = staleServerVersion !== null && !staleBannerDismissed;

  const {
    currentSession,
    fetchModelProviders,
    setCurrentSession,
    activeProjectId,
    activeProject,
    openProject,
    leaveProject,
    queuePendingSessionStarter,
    availableKnowledgeBases,
    loadKnowledgeBases,
  } = useChatStore();
  const { sessions } = useSessions();
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return true;
    const stored = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    // Default to collapsed unless the user explicitly expanded last time.
    return stored === null ? true : stored !== 'false';
  });
  const [mainView, setMainView] = useState<
    | 'chat'
    | 'knowledge'
    | 'assets'
    | 'browser'
    | 'project-list'
    | 'project-home'
    | 'project-chat'
    | 'settings'
    | 'tasks'
    | 'usage'
  >('chat');

  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [updatesRefreshing, setUpdatesRefreshing] = useState(false);
  // When set, the next render of <SettingsPage> opens with this section
  // pre-selected. Cleared once the user navigates somewhere else.
  const [settingsInitialSection, setSettingsInitialSection] = useState<SectionId | undefined>(undefined);
  // Poke a counter when the user dismisses banner/toast so the components
  // re-evaluate which announcements are still active without us refetching.
  const [, setUpdatesTick] = useState(0);

  const refreshVersionInfo = useCallback(async (forceRefresh: boolean) => {
    setUpdatesRefreshing(true);
    try {
      const info = await fetchVersionInfo({ forceRefresh });
      setVersionInfo(info);
    } finally {
      setUpdatesRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refreshVersionInfo(false);
    const interval = window.setInterval(() => {
      void refreshVersionInfo(true);
    }, POLL_INTERVAL_MS);
    return () => {
      window.clearInterval(interval);
    };
  }, [refreshVersionInfo]);

  // Poll pending skill suggestions and push them into the shared bell cache.
  // 45-second interval is a compromise: fast enough that a freshly minted
  // suggestion shows up before the user forgets the conversation that
  // produced it, slow enough to not spam the API.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const items = await api.listSkillSuggestions();
        if (cancelled) return;
        setPendingSkillSuggestions(items);
        // Bump the tick so anything that reads bell items (Header badge,
        // open AnnouncementPanel) re-renders without us having to thread
        // the suggestion array through every component.
        setUpdatesTick((v) => v + 1);
      } catch {
        // Silently ignore — the suggestions API may not be available yet
        // (e.g. backend still booting) and a transient failure shouldn't
        // hide existing items.
      }
    };
    void refresh();
    const handle = window.setInterval(() => void refresh(), 45_000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, []);

  const handleUpdatesDismissed = useCallback(() => {
    setUpdatesTick((value) => value + 1);
  }, []);

  const navigateToSkills = useCallback(() => {
    setSettingsInitialSection('skills');
    setMainView('settings');
  }, []);

  const handleManualRefresh = useCallback(() => {
    void refreshVersionInfo(true);
  }, [refreshVersionInfo]);

  useEffect(() => {
    void fetchModelProviders();
    void loadKnowledgeBases();
  }, [fetchModelProviders, loadKnowledgeBases]);

  // Surface chatStore.error (currently sprinkled across ~12 call sites but
  // never rendered) as a transient toast. After toasting we clear the field
  // so subsequent errors of the same text trigger a new toast.
  useEffect(() => {
    let lastError: string | null = useChatStore.getState().error;
    return useChatStore.subscribe((state) => {
      if (state.error && state.error !== lastError) {
        lastError = state.error;
        useToastStore.getState().pushToast(state.error, { level: 'error' });
        useChatStore.setState({ error: null });
        lastError = null;
      } else if (!state.error) {
        lastError = null;
      }
    });
  }, []);

  useEffect(() => {
    if (!currentSession) {
      return;
    }
    window.localStorage.setItem(LAST_SESSION_KEY, currentSession);
  }, [currentSession]);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed ? 'true' : 'false');
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (
      !shouldRestoreLastSession({
        currentSession,
        sessionCount: sessions.length,
        mainView,
        activeProjectId,
      })
    ) {
      return;
    }

    const rememberedSessionId = window.localStorage.getItem(LAST_SESSION_KEY);
    const restoredSession = sessions.find((session) => session.session_id === rememberedSessionId);
    setCurrentSession(restoredSession?.session_id || sessions[0].session_id);
  }, [currentSession, sessions, setCurrentSession, mainView, activeProjectId]);

  // First-time / fresh-start auto-onboarding: when no session is current and
  // there's nothing to restore, mint a new session id so ChatWindow renders
  // its welcome ("上午好,我能帮你做什么") screen instead of an empty
  // placeholder. For brand-new users this fires immediately; for returning
  // users we wait briefly so the restoration effect above wins.
  useEffect(() => {
    if (currentSession || mainView !== 'chat' || activeProjectId) return;
    const remembered = window.localStorage.getItem(LAST_SESSION_KEY);
    const mint = () =>
      setCurrentSession(
        `web:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      );
    if (!remembered) {
      mint();
      return;
    }
    // Last-session id exists — give restoration up to 300ms to find it.
    // Falls back to a fresh session if restoration can't (e.g., session was
    // deleted, or sessions list returned empty).
    const tid = window.setTimeout(() => {
      const state = useChatStore.getState();
      if (state.currentSession || state.activeProjectId) return;
      mint();
    }, 300);
    return () => window.clearTimeout(tid);
  }, [currentSession, mainView, activeProjectId, setCurrentSession]);

  return (
    <div className="app-root">
      <div
        className={[
          'app-shell',
          sidebarCollapsed ? 'app-shell--sidebar-collapsed' : '',
        ].join(' ')}
      >
        {showStaleBanner && staleServerVersion ? (
          <StaleClientBanner
            serverVersion={staleServerVersion}
            onRefresh={() => window.location.reload()}
            onDismiss={() => setStaleBannerDismissed(true)}
          />
        ) : null}
        <div className="app-main">
          <Sidebar
            collapsed={sidebarCollapsed}
            onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
            mainView={mainView}
            onSelectMainView={setMainView}
          />
          <main className="app-main__content">
            <Header
              versionInfo={versionInfo}
              onUpdatesChange={handleUpdatesDismissed}
              onRefreshUpdates={handleManualRefresh}
              updatesRefreshing={updatesRefreshing}
              onNavigateToSkills={navigateToSkills}
            />
            {mainView === 'settings' ? (
              <SettingsPage
                initialSection={settingsInitialSection}
                onNavigateBack={() => {
                  setSettingsInitialSection(undefined);
                  setMainView('chat');
                }}
                onNavigateToSession={(sessionId) => {
                  setSettingsInitialSection(undefined);
                  setCurrentSession(sessionId);
                  setMainView('chat');
                }}
              />
            ) : mainView === 'tasks' ? (
              <SettingsPage
                key="tasks-page"
                initialSection="automation"
                hideNav
                onNavigateBack={() => setMainView('chat')}
                onNavigateToSession={(sessionId) => {
                  setCurrentSession(sessionId);
                  setMainView('chat');
                }}
              />
            ) : mainView === 'assets' ? (
              <AssetsPage
                onNavigateToSession={async (sessionId, projectId) => {
                  if (projectId) {
                    // Hydrate the project + its session list first so chatStore can
                    // categorise the session correctly and the sidebar reflects the
                    // right project workspace before we switch the view.
                    try {
                      await openProject(projectId);
                    } catch {
                      // Fall through and still try to open the session by id.
                    }
                    setCurrentSession(sessionId);
                    setMainView('project-chat');
                  } else {
                    setCurrentSession(sessionId);
                    setMainView('chat');
                  }
                }}
              />
            ) : mainView === 'knowledge' ? (
              <KnowledgePage isActive />
            ) : mainView === 'browser' ? (
              <BrowserPage
                onStartChat={(prompt) => {
                  const sessionId = `web:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
                  queuePendingSessionStarter(sessionId, prompt);
                  setCurrentSession(sessionId);
                  setMainView('chat');
                }}
              />
            ) : mainView === 'usage' ? (
              <Suspense fallback={<div className="app-main__empty">加载中…</div>}>
                <UsagePage />
              </Suspense>
            ) : mainView === 'project-list' ? (
              <ProjectsGrid
                onOpenProject={(projectId) => {
                  void openProject(projectId).then(() => {
                    setMainView('project-home');
                  });
                }}
                onProjectCreated={() => setMainView('project-home')}
              />
            ) : mainView === 'project-home' ? (
              <ProjectHome
                onStartConversation={async (message) => {
                  const projectId = activeProjectId || activeProject?.id;
                  if (!projectId) {
                    return;
                  }

                  const sessionId = await createProjectConversation({
                    projectId,
                    message,
                    generateSessionId: () => `web:${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                    createProjectSession: async (projectId, nextSessionId) => {
                      await api.createProjectSession(projectId, nextSessionId);
                    },
                    queueSessionStarter: (content, nextSessionId) => {
                      queuePendingSessionStarter(nextSessionId, content);
                    },
                  });

                  setCurrentSession(sessionId);
                  setMainView('project-chat');
                }}
                onOpenSession={(sessionId) => {
                  setCurrentSession(sessionId);
                  setMainView('project-chat');
                }}
                onBack={() => {
                  leaveProject();
                  setMainView('project-list');
                }}
              />
            ) : currentSession ? (
              <ChatWindow
                sessionId={currentSession}
                onNavigateToSettings={() => setMainView('settings')}
                onNavigateToBrowser={() => setMainView('browser')}
              />
            ) : (
              <div className="app-main__empty">点击左侧“新建对话”开始新的会话</div>
            )}
          </main>
        </div>
      </div>
      <AttachmentPreview />
      <ToastContainer />
      <CommandPalette
        sessions={sessions}
        knowledgeBases={availableKnowledgeBases}
        onAction={(action: CommandPaletteAction) => {
          if (action.kind === 'open-session' && action.sessionId) {
            setCurrentSession(action.sessionId);
            setMainView('chat');
          } else if (action.kind === 'open-kb' && action.knowledgeBaseId) {
            setMainView('knowledge');
          } else if (action.kind === 'open-nav' && action.nav) {
            setMainView(action.nav);
          }
        }}
      />
      <AnnouncementToast info={versionInfo} />
      <UpdateModal info={versionInfo} onDismiss={handleUpdatesDismissed} />
      <CrossSessionApprovalToast
        onJumpToSession={(sessionId) => {
          setCurrentSession(sessionId);
          setMainView('chat');
        }}
      />
    </div>
  );
};

export default App;
