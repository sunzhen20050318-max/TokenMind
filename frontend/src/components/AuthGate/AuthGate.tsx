import { useCallback, useEffect, useRef, useState } from 'react';

import { getAuthSecret, setAuthSecret } from '../../services/apiAuth';
import './authGate.css';

interface AuthGateProps {
  children: React.ReactNode;
}

type Status = 'checking' | 'ok' | 'required';

/**
 * Front-end half of the LAN auth gate.
 *
 * 1. On mount: probe POST /api/auth/verify with whatever secret we already
 *    have in localStorage (may be empty).
 * 2. ``required: false`` → no secret configured on the backend, render the
 *    app. Localhost users go through this path.
 * 3. ``required: true, ok: true`` → stored secret is correct, render the
 *    app.
 * 4. Otherwise → show a centered card asking the user to paste the secret
 *    the desktop printed on first launch.
 */
export function AuthGate({ children }: AuthGateProps) {
  const [status, setStatus] = useState<Status>('checking');
  const [value, setValue] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const probe = useCallback(async () => {
    try {
      const res = await fetch('/api/auth/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ secret: getAuthSecret() }),
      });
      const json = (await res.json()) as { required?: boolean; ok?: boolean };
      if (json.required === false || json.ok) {
        setStatus('ok');
      } else {
        setStatus('required');
      }
    } catch {
      // Network blip — let the app try to render anyway, individual
      // requests will surface their own errors.
      setStatus('ok');
    }
  }, []);

  useEffect(() => {
    void probe();
  }, [probe]);

  useEffect(() => {
    if (status === 'required') {
      inputRef.current?.focus();
    }
  }, [status]);

  const submit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      const trimmed = value.trim();
      if (!trimmed) return;
      setSubmitting(true);
      setError(null);
      try {
        const res = await fetch('/api/auth/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ secret: trimmed }),
        });
        const json = (await res.json()) as { required?: boolean; ok?: boolean };
        if (json.ok) {
          setAuthSecret(trimmed);
          setStatus('ok');
        } else {
          setError('密钥不正确，请检查后重试。');
        }
      } catch {
        setError('网络错误，请稍后再试。');
      } finally {
        setSubmitting(false);
      }
    },
    [value],
  );

  if (status === 'checking') {
    return <div className="auth-gate auth-gate--checking" aria-busy="true" />;
  }

  if (status === 'ok') {
    return <>{children}</>;
  }

  return (
    <div className="auth-gate">
      <form className="auth-gate__card" onSubmit={submit}>
        <h1>TokenMind 访问密钥</h1>
        <p>
          这个 TokenMind 启用了 LAN 访问保护。请输入服务首次启动时打印的访问密钥，或在本机设置中心 →
          服务 → 访问密钥中复制。
        </p>
        <input
          ref={inputRef}
          className="auth-gate__input"
          type="password"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          placeholder="粘贴访问密钥"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          disabled={submitting}
        />
        {error ? <div className="auth-gate__error">{error}</div> : null}
        <button
          className="auth-gate__button"
          type="submit"
          disabled={submitting || !value.trim()}
        >
          {submitting ? '验证中…' : '进入 TokenMind'}
        </button>
        <p className="auth-gate__hint">
          本机（同台电脑上）打开 TokenMind 时不需要输入密钥；这个提示只会在手机或其他设备访问时出现。
        </p>
      </form>
    </div>
  );
}
