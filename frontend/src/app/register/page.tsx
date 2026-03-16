'use client';

import React, { useState, FormEvent } from 'react';
import Link from 'next/link';
import { register } from '@/lib/auth';
import { AuthShell } from '@/components/AuthShell/AuthShell';
import styles from '../login/login.module.css';

/**
 * 用户注册页。
 * 注册完成后保留同一视觉壳体，并直接引导邮箱验证。
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
      <strong>注册失败</strong>
      <span>{error}</span>
    </div>
  );

  const successView = (
    <div className={styles.successBox}>
      <h2>注册成功！</h2>
      <p>感谢您的注册。我们已经向您的邮箱 <strong>{email}</strong> 发送了一封验证邮件。</p>
      <p>请点击邮件中的链接以激活您的账户。</p>
      <p className={styles.successHint}>
        <strong>开发说明：</strong>
        如果本地未配置 SMTP，验证链接会输出在后端日志中。
      </p>
      <Link href="/login" className={styles.forgotLink}>
        返回登录
      </Link>
    </div>
  );

  const formView = (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.field}>
        <label className={styles.label} htmlFor="displayName">
          显示名称
        </label>
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
        <label className={styles.label} htmlFor="email">
          邮箱地址
        </label>
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
        <label className={styles.label} htmlFor="password">
          设置密码
        </label>
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
        <label className={styles.label} htmlFor="confirmPassword">
          确认密码
        </label>
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
      description={registrationSuccess ? '请前往收件箱完成验证后再登录。' : '创建账号后即可发起、审批并回看完整的 AI 内容工作流。'}
      eyebrow="开始使用"
      asideHeadline="让内容生成进入可编排状态"
      asideBody="PromptChain 把意图解析、提纲审批、事实核查和最终交付组织成可追踪、可确认、可重跑的工作流。"
      statusSlot={!registrationSuccess ? statusSlot : null}
      footerPrompt={registrationSuccess ? '没收到邮件？请检查垃圾邮件或联系管理员' : '已有账号？'}
      footerLink={registrationSuccess ? '' : '立即登录'}
      footerHref={!registrationSuccess ? '/login' : undefined}
    >
      {registrationSuccess ? successView : formView}
    </AuthShell>
  );
}
