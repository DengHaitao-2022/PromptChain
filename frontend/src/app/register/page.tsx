'use client';

import React, { useState, FormEvent } from 'react';
import Link from 'next/link';
import { register } from '@/lib/auth';
import { AuthShell } from '@/components/AuthShell/AuthShell';
import styles from '../login/login.module.css';

/**
 * RegisterPage: 注册页面
 * 遵循 AURA-X 电影感视觉风格，使用 AuthShell 布局
 * 注册成功后显示引导验证的成功态
 */
export default function RegisterPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [registrationSuccess, setRegistrationSuccess] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

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
      await register({
        email,
        password,
        display_name: displayName || undefined,
      });

      setRegistrationSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败，请稍后重试');
    } finally {
      setIsLoading(false);
    }
  };

  const statusSlot = error && (
    <div className={styles.errorBanner} role="alert">
      <span aria-hidden="true">⚠️</span>
      {error}
    </div>
  );

  const successView = (
    <div className={styles.successBox}>
      <h2>注册成功！</h2>
      <p>感谢您的注册。我们已经向您的邮箱 <strong>{email}</strong> 发送了一封验证邮件。</p>
      <p>请点击邮件中的链接以激活您的账户。</p>
      <p><small><strong>开发者提示：</strong>如果未配置 SMTP 服务，验证链接将输出在后端服务的日志中。</small></p>
      <Link href="/login" className={styles.forgotLink}>返回登录</Link>
    </div>
  );

  const formView = (
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
          disabled={isLoading}
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
          disabled={isLoading}
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
          disabled={isLoading}
        />
        <div className={styles.hint}>密码长度至少为 8 位</div>
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
          disabled={isLoading}
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
  );

  return (
    <AuthShell
      title={registrationSuccess ? '验证您的邮箱' : '创建您的账号'}
      description={registrationSuccess ? '请检查您的收件箱' : '开启 PromptChain 之旅。构建、编排并部署属于您的自主 AI 智能体工作流。'}
      eyebrow="开始使用"
      asideHeadline="从构思到自动化"
      asideBody="PromptChain 是专为开发者与团队设计的 AI 协作引擎。我们提供高性能的多智能体编排能力，让您的创意在数秒内转化为高效的工作流。"
      statusSlot={!registrationSuccess ? statusSlot : null}
      footerPrompt={registrationSuccess ? '邮箱没收到？' : '已有账号？'}
      footerLink={registrationSuccess ? '检查垃圾邮件或联系支持' : '立即登录'}
      footerHref={registrationSuccess ? 'mailto:support@example.com' : '/login'}
    >
      {registrationSuccess ? successView : formView}
    </AuthShell>
  );
}
