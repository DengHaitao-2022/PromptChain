'use client';

import React, { useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import NextLink from 'next/link';
import { AuthShell } from '../../components/AuthShell/AuthShell';
import { resetPassword } from '../../lib/auth';
import styles from '../login/login.module.css';

function ResetPasswordComponent() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [error, setError] = useState('');

  // 直接根据查询参数判断令牌状态，避免额外同步。
  const isTokenMissing = !token;
  const initialError = isTokenMissing ? '未提供重置令牌。请检查您的链接或重新申请。' : '';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (isTokenMissing) {
      setError('未提供重置令牌。请检查您的链接或重新申请。');
      setStatus('error');
      return;
    }

    if (password.length < 8) {
      setError('密码长度必须至少为8个字符。');
      setStatus('error');
      return;
    }

    if (password !== confirmPassword) {
      setError('两次输入的密码不匹配。');
      setStatus('error');
      return;
    }

    setStatus('loading');
    setError('');

    try {
      await resetPassword(token, password);
      setStatus('success');
    } catch {
      setStatus('error');
      setError('密码重置失败。令牌可能无效或已过期。');
    }
  };

  const aside = {
    asideHeadline: '更新访问密码',
    asideBody: '新密码将立即用于后续登录，请确保长度和强度满足要求。',
  };

  const currentError = error || initialError;

  const renderStatus = () => {
    if ((status === 'error' || isTokenMissing) && currentError) {
      return (
        <div className={styles.errorBanner}>
          <strong>重置失败</strong>
          <span>{currentError}</span>
        </div>
      );
    }
    return null;
  };

  if (status === 'success') {
    return (
      <AuthShell
        title="密码已重置"
        description="您现在可以使用新密码重新登录。"
        eyebrow="重置密码"
        asideHeadline={aside.asideHeadline}
        asideBody={aside.asideBody}
      >
        <div className={styles.successBox}>
          <h2>密码已更新</h2>
          <p>您的密码已成功更新。</p>
          <NextLink href="/login" className={styles.forgotLink}>
            返回登录
          </NextLink>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="创建新密码"
      description="您的新密码长度必须至少为8个字符。"
      eyebrow="重置密码"
      statusSlot={renderStatus()}
      asideHeadline={aside.asideHeadline}
      asideBody={aside.asideBody}
      footerPrompt="记起来了？"
      footerLink="返回登录"
      footerHref="/login"
    >
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.field}>
          <label htmlFor="password" className={styles.label}>
            新密码
          </label>
          <input
            id="password"
            name="password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={styles.input}
            placeholder="••••••••"
            minLength={8}
            autoComplete="new-password"
            disabled={status === 'loading' || isTokenMissing}
          />
          <div className={styles.hint}>建议至少使用 8 位，并混合大小写字母、数字或符号。</div>
        </div>
        <div className={styles.field}>
          <label htmlFor="confirmPassword" className={styles.label}>
            确认新密码
          </label>
          <input
            id="confirmPassword"
            name="confirmPassword"
            type="password"
            required
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className={styles.input}
            placeholder="••••••••"
            autoComplete="new-password"
            disabled={status === 'loading' || isTokenMissing}
          />
        </div>
        <button type="submit" className={styles.submitButton} disabled={status === 'loading' || isTokenMissing}>
          {status === 'loading' ? '正在重置...' : '重置密码'}
        </button>
      </form>
    </AuthShell>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <AuthShell
          title="创建新密码"
          description="正在加载重置页面。"
          eyebrow="重置密码"
          asideHeadline="更新访问密码"
          asideBody="新密码将立即用于后续登录，请确保长度和强度满足要求。"
          statusSlot={<div className={styles.helperText}>正在加载重置页面...</div>}
        >
          {null}
        </AuthShell>
      }
    >
      <ResetPasswordComponent />
    </Suspense>
  );
}
