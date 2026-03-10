'use client';

import React, { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { register } from '@/lib/auth';
import { AuthShell } from '@/components/AuthShell/AuthShell';
import styles from '../login/login.module.css';

/**
 * RegisterPage: 注册页面
 * 遵循 AURA-X 电影感视觉风格，使用 AuthShell 布局
 */
export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    // 客户端校验
    if (password !== confirmPassword) {
      setError('两次输入的密码不一致');
      return;
    }

    if (password.length < 8) {
      setError('密码长度至少为 8 位');
      return;
    }

    setIsLoading(true);

    try {
      const result = await register({
        email,
        password,
        display_name: displayName || undefined,
      });

      setSuccess(result.message || '账号注册成功！正在跳转到登录页面...');

      // 3 秒后跳转到登录页面
      setTimeout(() => {
        router.push('/login');
      }, 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败，请稍后重试');
    } finally {
      setIsLoading(false);
    }
  };

  const statusSlot = (
    <>
      {error && (
        <div className={styles.errorBanner} role="alert">
          <span aria-hidden="true">⚠️</span>
          {error}
        </div>
      )}
      {success && (
        <div className={styles.successBanner} role="status">
          <span aria-hidden="true">✅</span>
          {success}
        </div>
      )}
    </>
  );

  return (
    <AuthShell
      title="创建您的账号"
      description="开启 PromptChain 之旅。构建、编排并部署属于您的自主 AI 智能体工作流。"
      eyebrow="开始使用"
      asideHeadline="从构思到自动化。"
      asideBody="PromptChain 是专为开发者与团队设计的 AI 协作引擎。我们提供高性能的多智能体编排能力，让您的创意在数秒内转化为高效的工作流。"
      statusSlot={statusSlot}
      footerPrompt="已有账号？"
      footerLink="立即登录"
      footerHref="/login"
    >
      <form onSubmit={handleSubmit} className={styles.form}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="displayName">显示名称</label>
          <input
            id="displayName"
            className={styles.input}
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="您的昵称或真实姓名"
            autoComplete="name"
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="email">邮箱地址</label>
          <input
            id="email"
            className={styles.input}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@example.com"
            required
            autoComplete="email"
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="password">设置密码</label>
          <input
            id="password"
            className={styles.input}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            minLength={8}
            autoComplete="new-password"
          />
          <div className={styles.hint}>密码长度至少为 8 位，建议包含字母与数字</div>
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="confirmPassword">确认密码</label>
          <input
            id="confirmPassword"
            className={styles.input}
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="请再次确认您的密码"
            required
            autoComplete="new-password"
          />
        </div>

        <button
          type="submit"
          className={styles.submitButton}
          disabled={isLoading}
        >
          {isLoading ? '注册中...' : '立即注册'}
        </button>
      </form>
    </AuthShell>
  );
}
