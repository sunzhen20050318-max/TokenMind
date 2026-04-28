import React, { useState } from 'react';
import {
  selectRunningTasks,
  useCreativeTasksStore,
  type CreativeTask,
} from '../../stores/creativeTasksStore';
import type { SidebarMainView } from '../Layout/Sidebar';
import './creativeTasksDock.css';

interface CreativeTasksDockProps {
  collapsed: boolean;
  onSelectMainView: (view: SidebarMainView) => void;
}

const KIND_LABEL: Record<CreativeTask['kind'], string> = {
  music: '音乐',
  'voice-clone': '声音克隆',
  tts: '语音合成',
  'voice-design': '音色设计',
};

const KIND_TARGET: Record<CreativeTask['kind'], SidebarMainView> = {
  music: 'music',
  'voice-clone': 'voice-clone',
  tts: 'tts',
  'voice-design': 'voice-design',
};

/**
 * Sidebar dock that surfaces in-flight creative tasks (music / voice clone /
 * TTS / voice design). Lets the user click a row to jump to the studio that
 * owns the task, even if they navigated to settings or chat in the meantime.
 */
export const CreativeTasksDock: React.FC<CreativeTasksDockProps> = ({
  collapsed,
  onSelectMainView,
}) => {
  const runningTasks = useCreativeTasksStore(selectRunningTasks);
  const [open, setOpen] = useState(false);

  if (runningTasks.length === 0) {
    return null;
  }

  if (collapsed) {
    return (
      <button
        type="button"
        className="creative-tasks-dock creative-tasks-dock--collapsed"
        title={`${runningTasks.length} 个任务进行中`}
        aria-label={`${runningTasks.length} 个任务进行中`}
        onClick={() => onSelectMainView(KIND_TARGET[runningTasks[0].kind])}
      >
        <span className="creative-tasks-dock__pulse" aria-hidden="true" />
        <span className="creative-tasks-dock__count">{runningTasks.length}</span>
      </button>
    );
  }

  return (
    <div className={`creative-tasks-dock ${open ? 'is-open' : ''}`}>
      <button
        type="button"
        className="creative-tasks-dock__head"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className="creative-tasks-dock__pulse" aria-hidden="true" />
        <span className="creative-tasks-dock__title">{runningTasks.length} 个任务进行中</span>
        <span className={`creative-tasks-dock__caret ${open ? 'is-open' : ''}`}>▾</span>
      </button>

      {open ? (
        <ul className="creative-tasks-dock__list">
          {runningTasks.map((task) => (
            <li key={task.id}>
              <button
                type="button"
                className="creative-tasks-dock__item"
                onClick={() => {
                  onSelectMainView(KIND_TARGET[task.kind]);
                  setOpen(false);
                }}
                title={task.label}
              >
                <span className="creative-tasks-dock__kind">{KIND_LABEL[task.kind]}</span>
                <span className="creative-tasks-dock__label">{task.label}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};
