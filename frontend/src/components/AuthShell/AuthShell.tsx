'use client';

import React from 'react';
import NextLink from 'next/link';
import styles from './AuthShell.module.css';

interface AuthShellProps {
  /** Main title of the auth card */
  title: string;
  /** Description or sub-text for the auth card */
  description?: string;
  /** Eyebrow text above the aside headline */
  eyebrow?: string;
  /** Large headline in the brand panel */
  asideHeadline: string;
  /** Supporting text in the brand panel */
  asideBody: string;
  /** Slot for status messages, errors, or loaders */
  statusSlot?: React.ReactNode;
  /** Text prompt before the footer link */
  footerPrompt?: string;
  /** Text for the footer navigation link */
  footerLink?: string;
  /** Href for the footer navigation link */
  footerHref?: string;
  /** Form or primary content */
  children: React.ReactNode;
}

/**
 * AuthShell: A high-fidelity, cinema-inspired layout for authentication pages.
 * Features a layered graphite aesthetic with electric-cyan accents.
 */
export const AuthShell: React.FC<AuthShellProps> = ({
  title,
  description,
  eyebrow,
  asideHeadline,
  asideBody,
  statusSlot,
  footerPrompt,
  footerLink,
  footerHref,
  children,
}) => {
  return (
    <div className={styles.container}>
      {/* Brand Panel - Visible on Desktop */}
      <aside className={styles.aside}>
        <div className={styles.asideGlow} aria-hidden="true" />

        <div className={styles.asideHeader}>
          <NextLink href="/" className={styles.logo}>
            PromptChain
            <span className={styles.logoDot} />
          </NextLink>
        </div>

        <div className={styles.asideContent}>
          {eyebrow && <div className={styles.eyebrow}>{eyebrow}</div>}
          <h1 className={styles.headline}>{asideHeadline}</h1>
          <p className={styles.body}>{asideBody}</p>

          <div className={styles.trustGroup}>
            <div className={styles.chip}>
              <span className={styles.chipIcon}>⚡</span>
              <span>极低延迟推理</span>
            </div>
            <div className={styles.chip}>
              <span className={styles.chipIcon}>🛡️</span>
              <span>企业级安全保障</span>
            </div>
            <div className={styles.chip}>
              <span className={styles.chipIcon}>🤖</span>
              <span>自主多智能体编排</span>
            </div>
          </div>
        </div>

        <footer className={styles.asideFooter}>
          <p>&copy; 2026 PromptChain Engine. 为神经工作流优化。</p>
        </footer>
      </aside>

      {/* Main Form Surface */}
      <main className={styles.main}>
        <div className={styles.cardContainer}>
          <div className={styles.cardGlow} aria-hidden="true" />

          <div className={styles.card}>
            <header className={styles.header}>
              <h2 className={styles.title}>{title}</h2>
              {description && <p className={styles.description}>{description}</p>}
            </header>

            {statusSlot && <div className={styles.statusArea}>{statusSlot}</div>}

            <div className={styles.formArea}>{children}</div>

            {(footerPrompt || footerLink) && (
              <footer className={styles.formFooter}>
                {footerPrompt && <span className={styles.prompt}>{footerPrompt}</span>}
                {footerLink && footerHref && (
                  <NextLink href={footerHref} className={styles.link}>
                    {footerLink}
                  </NextLink>
                )}
              </footer>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};
