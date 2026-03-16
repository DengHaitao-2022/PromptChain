'use client';

import React, { useState } from 'react';
import { AuthShell } from '../../components/AuthShell/AuthShell';
import { forgotPassword } from '../../lib/auth';
import styles from '../login/login.module.css';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success'>('idle');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('loading');

    try {
      await forgotPassword(email);
      setStatus('success');
    } catch {
      // 无论接口结果如何，都返回统一提示，避免泄露邮箱是否存在。
      setStatus('success');
    }
  };

  const aside = {
    asideHeadline: '通过安全链接恢复访问',
    asideBody: '认证入口会统一回到可审计链路，密码恢复流程同样不暴露账户存在状态。',
  };

  const renderStatus = () => {
    if (status === 'success') {
      return (
        <div className={styles.successBanner}>
          <strong>请求已提交</strong>
          <span>如果该邮箱已注册，系统会向您发送密码重置链接。</span>
        </div>
      );
    }
    return null;
  };

  return (
    <AuthShell
      title="重置密码"
      description="请输入您的登录邮箱，我们会发送一封安全的密码重置邮件。"
      eyebrow="密码恢复"
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
              placeholder="name@company.com"
              disabled={status === 'loading'}
            />
            <div className={styles.hint}>出于安全考虑，我们不会透露该邮箱是否已注册。</div>
          </div>
          <button type="submit" className={styles.submitButton} disabled={status === 'loading'}>
            {status === 'loading' ? '发送中...' : '发送重置邮件'}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
