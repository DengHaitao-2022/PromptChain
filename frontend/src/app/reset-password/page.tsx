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

  // 移除了 useEffect，直接在渲染逻辑中处理 token 缺失
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
    asideHeadline: '设置新密码',
    asideBody: '为了账户安全，请设置一个高强度的新密码。',
  };

  const currentError = error || initialError;

  const renderStatus = () => {
    if ((status === 'error' || isTokenMissing) && currentError) {
      return <div className={styles.errorBanner}>{currentError}</div>;
    }
    return null;
  };

  if (status === 'success') {
    return (
        <AuthShell
            title="密码已重置"
            asideHeadline={aside.asideHeadline}
            asideBody={aside.asideBody}
        >
             <div className={styles.successBox}>
                <h2>✅ 重置成功</h2>
                <p>您的密码已成功更新。</p>
                <NextLink href="/login" className={styles.forgotLink}>
                点击这里返回登录
                </NextLink>
            </div>
        </AuthShell>
    );
  }

  return (
    <AuthShell
      title="创建新密码"
      description="您的新密码长度必须至少为8个字符。"
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
            disabled={status === 'loading' || isTokenMissing}
          />
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
        <Suspense fallback={<div>Loading...</div>}>
            <ResetPasswordComponent />
        </Suspense>
    )
}
