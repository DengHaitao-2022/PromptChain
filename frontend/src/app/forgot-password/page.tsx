'use client';

import React, { useState } from 'react';
import { AuthShell } from '../../components/AuthShell/AuthShell';
import { forgotPassword } from '../../lib/auth';
import styles from '../login/login.module.css';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('loading');
    setError('');

    try {
      await forgotPassword(email);
      // Per requirements, always show a generic success message
      setStatus('success');
    } catch {
      // Even in case of error, we show the same message
      // to prevent email enumeration attacks.
      setStatus('success');
    }
  };

  const aside = {
    asideHeadline: '忘记密码？',
    asideBody: '我们将通过安全的链接，帮助您重获账户访问权限。',
  };

  const renderStatus = () => {
    if (status === 'success') {
      return (
        <div className={styles.successBanner}>
           如果该电子邮件地址在我们系统中注册，您将很快收到密码重置链接。
        </div>
      );
    }
    if (status === 'error' && error) {
      return <div className={styles.errorBanner}>{error}</div>;
    }
    return null;
  };

  return (
    <AuthShell
      title="重置密码"
      description="请输入您的电子邮件地址，我们将发送给您一个重置链接。"
      statusSlot={renderStatus()}
      asideHeadline={aside.asideHeadline}
      asideBody={aside.asideBody}
      footerPrompt="记起来了？"
      footerLink="返回登录"
      footerHref="/login"
    >
      {status !== 'success' && (
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label htmlFor="email" className={styles.label}>
              电子邮件地址
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={styles.input}
              placeholder="you@example.com"
              disabled={status === 'loading'}
            />
          </div>
          <button type="submit" className={styles.submitButton} disabled={status === 'loading'}>
            {status === 'loading' ? '发送中...' : '发送重置邮件'}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
