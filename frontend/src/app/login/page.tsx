'use client';

import React, { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Eye, EyeOff } from 'lucide-react';
import { login } from '@/lib/auth';
import { AuthShell } from '@/components/AuthShell/AuthShell';
import styles from './login.module.css';

function getSafeNextPath() {
  if (typeof window === 'undefined') {
    return null;
  }

  const nextPath = new URLSearchParams(window.location.search).get('next');
  if (!nextPath || !nextPath.startsWith('/') || nextPath.startsWith('//')) {
    return null;
  }

  return nextPath;
}

/**
 * 用户登录页。
 * 使用统一认证壳体承接首页延展出的视觉语言。
 */
export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [isPasswordVisible, setIsPasswordVisible] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login({ email, password });
      router.push(getSafeNextPath() || '/console');
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请检查邮箱和密码是否正确');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <AuthShell
      title="登录控制台"
      description="使用企业账号继续访问工作区"
      eyebrow="AI Workflow Platform"
      asideHeadline={'让 AI 工作流\n可追踪、可审批、\n可交付'}
      asideBody="从任务发起到运行审查，统一管理关键节点，保障流程透明、版本可控。"
      footerPrompt="没有访问权限？联系管理员"
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
            placeholder="请输入企业邮箱"
            className={styles.input}
            required
            autoComplete="email"
            disabled={isLoading}
          />
        </div>

        <div className={styles.field}>
          <label htmlFor="password" className={styles.label}>
            登录密码
          </label>
          <div className={styles.inputWrap}>
            <input
              id="password"
              type={isPasswordVisible ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入登录密码"
              className={`${styles.input} ${styles.inputWithAction}`}
              required
              autoComplete="current-password"
              disabled={isLoading}
            />
            <button
              type="button"
              className={styles.inputAction}
              aria-label={isPasswordVisible ? '隐藏密码' : '显示密码'}
              aria-pressed={isPasswordVisible}
              onClick={() => setIsPasswordVisible((visible) => !visible)}
              disabled={isLoading}
            >
              {isPasswordVisible ? <EyeOff size={20} aria-hidden="true" /> : <Eye size={20} aria-hidden="true" />}
            </button>
          </div>
        </div>

        <div className={styles.helperRow}>
          <label className={styles.rememberToggle}>
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className={styles.checkboxInput}
              disabled={isLoading}
            />
            <span className={styles.checkboxBox} aria-hidden="true" />
            <span className={styles.checkboxLabel}>记住我</span>
          </label>

          <Link href="/forgot-password" className={styles.metaLink}>
            忘记密码？
          </Link>
        </div>

        <button
          type="submit"
          className={styles.submitButton}
          disabled={isLoading}
        >
          {isLoading ? '登录中...' : '登录控制台'}
        </button>
      </form>
    </AuthShell>
  );
}
