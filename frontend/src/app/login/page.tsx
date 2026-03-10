'use client';

import React, { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { login } from '@/lib/auth';
import { AuthShell } from '@/components/AuthShell/AuthShell';
import styles from './login.module.css';

/**
 * LoginPage: 用户登录页面
 * 使用 AuthShell 提供的电影感深色主题布局
 */
export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login({ email, password });
      router.push('/console');
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请检查您的凭据');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <AuthShell
      title="欢迎回来"
      description="请使用您的电子邮件和密码访问 PromptChain 仪表板"
      eyebrow="NEXT-GEN ORCHESTRATION"
      asideHeadline="连接智能，编排未来"
      asideBody="基于多智能体协作的自动化工作流引擎，为企业提供极致的生产力工具。"
      footerPrompt="还没有账号？"
      footerLink="立即注册"
      footerHref="/register"
      statusSlot={
        error && (
          <div className={styles.errorBanner} role="alert">
            <span aria-hidden="true">⚠️</span>
            {error}
          </div>
        )
      }
    >
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.field}>
          <label htmlFor="email" className={styles.label}>
            电子邮箱
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@company.com"
            className={styles.input}
            required
            autoComplete="email"
            disabled={isLoading}
          />
        </div>

        <div className={styles.field}>
          <label htmlFor="password" className={styles.label}>
            访问密码
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            className={styles.input}
            required
            autoComplete="current-password"
            disabled={isLoading}
          />
        </div>

        <div className={styles.actionsRow}>
          <Link href="/forgot-password" className={styles.forgotLink}>
            忘记密码？
          </Link>
        </div>

        <button
          type="submit"
          className={styles.submitButton}
          disabled={isLoading}
        >
          {isLoading ? '正在验证身份...' : '进入控制台'}
        </button>
      </form>
    </AuthShell>
  );
}
