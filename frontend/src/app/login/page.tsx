'use client';

import React, { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { login } from '@/lib/auth';
import { AuthShell } from '@/components/AuthShell/AuthShell';
import styles from './login.module.css';

/**
 * 用户登录页。
 * 使用统一认证壳体承接首页延展出的视觉语言。
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
      description="登录后继续查看运行状态、审批节点和版本化产物。"
      eyebrow="认证入口"
      asideHeadline="进入可追踪的 AI 工作流控制台"
      asideBody="从首页启动，到运行态审批、事实核查和内容交付，所有关键节点都保持可见。"
      footerPrompt="还没有账号？"
      footerLink="立即注册"
      footerHref="/register"
      statusSlot={
        error && (
          <div className={styles.errorBanner} role="alert">
            <strong>登录失败</strong>
            <span>{error}</span>
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
            placeholder="请输入登录密码"
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
