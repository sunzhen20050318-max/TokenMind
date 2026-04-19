import React, { useEffect, useMemo, useRef, useState } from 'react';
import { BrandMark } from '../BrandMark';
import './entryGate.css';

interface EntryGateProps {
  onEnter: () => void;
  isExiting: boolean;
}

const PARTICLES = [
  { left: '9%', top: '16%', delay: '0s', duration: '11s' },
  { left: '18%', top: '74%', delay: '1.6s', duration: '13s' },
  { left: '27%', top: '28%', delay: '0.8s', duration: '10.5s' },
  { left: '39%', top: '12%', delay: '2.3s', duration: '14s' },
  { left: '48%', top: '82%', delay: '0.4s', duration: '12s' },
  { left: '59%', top: '32%', delay: '1.2s', duration: '9.5s' },
  { left: '67%', top: '68%', delay: '2.8s', duration: '12.5s' },
  { left: '78%', top: '22%', delay: '0.6s', duration: '11.5s' },
  { left: '86%', top: '58%', delay: '1.9s', duration: '13.5s' },
];

const SWIPE_THRESHOLD = 88;
const WHEEL_THRESHOLD = -44;
const WORDMARK_TEXT = 'TokenMind';
const TAGLINE_TEXT = 'YOUR PERSONAL AI ASSISTANT';

export const EntryGate: React.FC<EntryGateProps> = ({ onEnter, isExiting }) => {
  const rootRef = useRef<HTMLDivElement>(null);
  const touchStartYRef = useRef<number | null>(null);
  const targetPointerRef = useRef({ x: 0.5, y: 0.5 });
  const currentPointerRef = useRef({ x: 0.5, y: 0.5 });
  const rafRef = useRef<number | null>(null);
  const [dragOffset, setDragOffset] = useState(0);
  const [typedWordmark, setTypedWordmark] = useState('');
  const [typedTagline, setTypedTagline] = useState('');
  const [typingStage, setTypingStage] = useState<'wordmark' | 'tagline' | 'done'>('wordmark');

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (isExiting) {
        return;
      }

      if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowUp') {
        event.preventDefault();
        onEnter();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isExiting, onEnter]);

  useEffect(() => {
    const tick = () => {
      const root = rootRef.current;
      if (root) {
        const current = currentPointerRef.current;
        const target = targetPointerRef.current;

        current.x += (target.x - current.x) * 0.085;
        current.y += (target.y - current.y) * 0.085;

        const shiftX = (current.x - 0.5) * 2;
        const shiftY = (current.y - 0.5) * 2;

        root.style.setProperty('--pointer-x', `${(current.x * 100).toFixed(2)}%`);
        root.style.setProperty('--pointer-y', `${(current.y * 100).toFixed(2)}%`);
        root.style.setProperty('--pointer-shift-x', shiftX.toFixed(4));
        root.style.setProperty('--pointer-shift-y', shiftY.toFixed(4));
      }

      rafRef.current = window.requestAnimationFrame(tick);
    };

    rafRef.current = window.requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) {
        window.cancelAnimationFrame(rafRef.current);
      }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timeoutId: number | null = null;

    const queue = (callback: () => void, delay: number) => {
      timeoutId = window.setTimeout(() => {
        if (!cancelled) {
          callback();
        }
      }, delay);
    };

    const typeText = (
      fullText: string,
      setter: React.Dispatch<React.SetStateAction<string>>,
      stepMs: number,
      onDone: () => void
    ) => {
      let index = 0;

      const run = () => {
        setter(fullText.slice(0, index + 1));
        index += 1;

        if (index < fullText.length) {
          queue(run, stepMs);
        } else {
          onDone();
        }
      };

      run();
    };

    setTypedWordmark('');
    setTypedTagline('');
    setTypingStage('wordmark');

    queue(() => {
      typeText(WORDMARK_TEXT, setTypedWordmark, 105, () => {
        setTypingStage('tagline');
        queue(() => {
          typeText(TAGLINE_TEXT, setTypedTagline, 34, () => {
            setTypingStage('done');
          });
        }, 180);
      });
    }, 220);

    return () => {
      cancelled = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    };
  }, []);

  const gateStyle = useMemo(
    () =>
      ({
        '--entry-drag': `${dragOffset}px`,
      }) as React.CSSProperties,
    [dragOffset]
  );

  const updatePointerTarget = (clientX: number, clientY: number) => {
    const root = rootRef.current;
    if (!root) {
      return;
    }

    const rect = root.getBoundingClientRect();
    const x = (clientX - rect.left) / rect.width;
    const y = (clientY - rect.top) / rect.height;

    targetPointerRef.current = {
      x: Math.max(0, Math.min(1, x)),
      y: Math.max(0, Math.min(1, y)),
    };
  };

  const handleTouchMove = (event: React.TouchEvent<HTMLDivElement>) => {
    if (touchStartYRef.current === null || isExiting) {
      return;
    }

    updatePointerTarget(event.touches[0].clientX, event.touches[0].clientY);

    const delta = touchStartYRef.current - event.touches[0].clientY;
    setDragOffset(Math.max(0, Math.min(delta, 160)));
  };

  const handleTouchEnd = () => {
    if (isExiting) {
      return;
    }

    if (dragOffset >= SWIPE_THRESHOLD) {
      onEnter();
    }

    touchStartYRef.current = null;
    setDragOffset(0);
    targetPointerRef.current = { x: 0.5, y: 0.5 };
  };

  return (
    <div
      ref={rootRef}
      className={`entry-gate ${isExiting ? 'entry-gate--exit' : ''}`}
      style={gateStyle}
      onClick={() => {
        if (!isExiting) {
          onEnter();
        }
      }}
      onMouseLeave={() => {
        targetPointerRef.current = { x: 0.5, y: 0.5 };
      }}
      onMouseMove={(event) => updatePointerTarget(event.clientX, event.clientY)}
      onTouchEnd={handleTouchEnd}
      onTouchMove={handleTouchMove}
      onTouchStart={(event) => {
        if (!isExiting) {
          touchStartYRef.current = event.touches[0].clientY;
          updatePointerTarget(event.touches[0].clientX, event.touches[0].clientY);
        }
      }}
      onWheel={(event) => {
        if (!isExiting && event.deltaY <= WHEEL_THRESHOLD) {
          onEnter();
        }
      }}
      role="button"
      tabIndex={0}
      aria-label="进入 TokenMind"
    >
      <div className="entry-gate__ambient" />
      <div className="entry-gate__spotlight" />
      <div className="entry-gate__mesh entry-gate__mesh--far" />
      <div className="entry-gate__mesh entry-gate__mesh--near" />

      <svg className="entry-gate__sweep" viewBox="0 0 1440 1024" aria-hidden="true">
        <path className="entry-gate__sweep-path entry-gate__sweep-path--one" d="M-120 622C140 532 330 490 514 514C702 538 900 642 1126 654C1280 662 1392 630 1548 566" />
        <path className="entry-gate__sweep-path entry-gate__sweep-path--two" d="M-160 432C86 364 252 332 418 344C584 356 742 420 908 454C1078 490 1256 492 1526 422" />
        <path className="entry-gate__sweep-path entry-gate__sweep-path--three" d="M-140 778C108 724 314 684 504 700C708 716 876 802 1100 818C1250 828 1380 796 1540 744" />
      </svg>

      <div className="entry-gate__particles" aria-hidden="true">
        {PARTICLES.map((particle, index) => (
          <span
            key={`${particle.left}-${particle.top}`}
            className={`entry-gate__particle entry-gate__particle--${(index % 3) + 1}`}
            style={{
              left: particle.left,
              top: particle.top,
              animationDelay: particle.delay,
              animationDuration: particle.duration,
            }}
          />
        ))}
      </div>

      <header className="entry-gate__brand">
        <div className="entry-gate__brand-mark" aria-hidden="true">
          <BrandMark size={24} alt="" />
        </div>
      </header>

      <main className="entry-gate__center">
        <div className="entry-gate__rings" aria-hidden="true">
          <div className="entry-gate__ring entry-gate__ring--outer" />
          <div className="entry-gate__ring entry-gate__ring--mid" />
          <div className="entry-gate__ring entry-gate__ring--inner" />
          <div className="entry-gate__orbital entry-gate__orbital--one">
            <span />
          </div>
          <div className="entry-gate__orbital entry-gate__orbital--two">
            <span />
          </div>
          <div className="entry-gate__orbital entry-gate__orbital--three">
            <span />
          </div>
        </div>

        <div className="entry-gate__wordmark-wrap">
          <div className="entry-gate__wordmark-shell">
            <div
              className={`entry-gate__wordmark ${typingStage === 'wordmark' ? 'is-typing' : ''}`}
              aria-label={WORDMARK_TEXT}
            >
              {typedWordmark}
            </div>
          </div>
          <div className="entry-gate__tagline-shell">
            <div
              className={`entry-gate__tagline ${typingStage === 'tagline' ? 'is-typing' : ''}`}
              aria-label={TAGLINE_TEXT}
            >
              {typedTagline}
            </div>
          </div>
        </div>

        <div className="entry-gate__microcopy">
          <p>点击任意位置进入</p>
          <p>或上滑 / Enter</p>
        </div>
      </main>

      <footer className="entry-gate__footer">
        <div className="entry-gate__footer-line" />
        <button
          className="entry-gate__cta"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            if (!isExiting) {
              onEnter();
            }
          }}
        >
          Enter
        </button>
      </footer>
    </div>
  );
};
