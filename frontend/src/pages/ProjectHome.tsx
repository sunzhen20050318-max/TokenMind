import React, { useMemo, useState } from 'react';
import { ProjectEntryComposer } from '../components/Projects/ProjectEntryComposer';
import { buildProjectEntryState } from '../components/Projects/projectEntryState';
import { useChatStore } from '../stores/chatStore';
import '../components/Projects/projects.css';

interface ProjectHomeProps {
  onStartConversation: (message: string) => Promise<void> | void;
  onOpenSession: (sessionId: string) => void;
}

const PROJECT_LABEL = '\u9879\u76ee';
const PROJECT_SPACE_LABEL = '\u9879\u76ee\u7a7a\u95f4';
const STARTER_SUFFIX = '\u4e2d\u7684\u65b0\u804a\u5929';
const SECTION_CHAT = '\u804a\u5929';
const SECTION_LOG = '\u9879\u76ee\u8bb0\u5f55';
const FALLBACK_SESSION = '\u65b0\u5bf9\u8bdd';
const FALLBACK_SUMMARY = '\u70b9\u51fb\u7ee7\u7eed\u8fd9\u6bb5\u9879\u76ee\u5185\u5bf9\u8bdd';
const HEADER_COPY =
  '\u8fd9\u91cc\u7684\u804a\u5929\u53ea\u5c5e\u4e8e\u5f53\u524d\u9879\u76ee\uff0c\u4e0d\u4f1a\u51fa\u73b0\u5728\u5de6\u4fa7\u5168\u5c40\u6700\u8fd1\u4f1a\u8bdd\u91cc\u3002';
const SUBMIT_ERROR = '\u521b\u5efa\u9879\u76ee\u804a\u5929\u5931\u8d25';

export const ProjectHome: React.FC<ProjectHomeProps> = ({ onStartConversation, onOpenSession }) => {
  const { projects, activeProjectId, activeProject, projectSessions } = useChatStore();
  const project = activeProject || projects.find((item) => item.id === activeProjectId);
  const [draft, setDraft] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const entryState = useMemo(
    () =>
      buildProjectEntryState({
        projectName: project?.name || PROJECT_LABEL,
        sessions: projectSessions,
      }),
    [project?.name, projectSessions]
  );

  const handleSubmit = async () => {
    const trimmed = draft.trim();
    if (!trimmed || isSubmitting) {
      return;
    }

    setSubmitError(null);
    setIsSubmitting(true);

    try {
      await onStartConversation(trimmed);
      setDraft('');
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : SUBMIT_ERROR);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="project-home">
      <div className="project-home__body">
        <header className="project-home__header is-entry">
          <p className="project-home__eyebrow">{PROJECT_SPACE_LABEL}</p>
          <div className="project-home__identity">
            <span className="project-home__icon" aria-hidden="true">
              <span />
            </span>
            <div className="project-home__identity-copy">
              <h1>{entryState.title}</h1>
              <p>{HEADER_COPY}</p>
            </div>
          </div>
        </header>

        <ProjectEntryComposer
          value={draft}
          onChange={setDraft}
          onSubmit={() => {
            void handleSubmit();
          }}
          disabled={isSubmitting}
          placeholder={`${entryState.title} ${STARTER_SUFFIX}`}
        />

        {submitError ? <div className="project-home__error">{submitError}</div> : null}

        <div className="project-home__section-tabs" aria-hidden="true">
          <span className="is-active">{SECTION_CHAT}</span>
          <span>{SECTION_LOG}</span>
        </div>

        {entryState.showEmptyHint ? (
          <p className="project-home__inline-empty">{entryState.emptyHint}</p>
        ) : (
          <div className="project-home__list">
            {projectSessions.map((session) => (
              <button
                key={session.session_id}
                type="button"
                className="project-home__item"
                onClick={() => onOpenSession(session.session_id)}
              >
                <div className="project-home__item-main">
                  <strong>{session.title || session.first_message || FALLBACK_SESSION}</strong>
                  <span>{session.first_message || FALLBACK_SUMMARY}</span>
                </div>
                <small>
                  {session.updated_at
                    ? new Date(session.updated_at).toLocaleDateString('zh-CN', {
                        month: 'numeric',
                        day: 'numeric',
                      })
                    : ''}
                </small>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};
