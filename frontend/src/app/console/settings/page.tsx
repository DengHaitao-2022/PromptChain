'use client';

/**
 * 设置总览页
 */

import Link from 'next/link';
import { Bot, KeyRound, ScrollText, Settings2, Users } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import styles from './settings.module.css';

type SettingsCard = {
  href: string;
  title: string;
  description: string;
  metric: string;
  resource: 'member' | 'model_provider' | 'secret' | 'audit_log';
  icon: typeof Users;
};

const SETTINGS_CARDS: SettingsCard[] = [
  {
    href: '/console/settings/members',
    title: '成员管理',
    description: '管理工作空间成员、角色和当前工作空间访问边界。',
    metric: '协作权限',
    resource: 'member',
    icon: Users,
  },
  {
    href: '/console/settings/models',
    title: '模型配置',
    description: '维护模型供应商、启用状态和推理接入策略。',
    metric: '模型入口',
    resource: 'model_provider',
    icon: Bot,
  },
  {
    href: '/console/settings/keys',
    title: '密钥管理',
    description: '统一托管平台密钥与对外 API Key 生命周期。',
    metric: '安全凭证',
    resource: 'secret',
    icon: KeyRound,
  },
  {
    href: '/console/settings/audit',
    title: '审计日志',
    description: '回看关键操作事件，支持排障、追溯与安全审计。',
    metric: '操作追踪',
    resource: 'audit_log',
    icon: ScrollText,
  },
];

export default function SettingsOverviewPage() {
  const { hasPermission } = useAuth();

  const visibleCards = SETTINGS_CARDS.filter((card) => hasPermission(card.resource, 'read'));

  return (
    <div className={styles.container}>
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <span className={styles.eyebrow}>System Settings</span>
          <h1 className={styles.title}>设置总览</h1>
          <p className={styles.subtitle}>
            从这里进入成员、模型、密钥和审计模块。所有页面都共享同一套主题 token、状态语义和控制台壳体。
          </p>
        </div>

        <div className={styles.summaryGrid}>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>可访问模块</span>
            <span className={styles.summaryValue}>{visibleCards.length}</span>
            <span className={styles.summaryMeta}>按当前角色过滤后仍然可进入的设置板块数量</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>管理维度</span>
            <span className={styles.summaryValue}>4</span>
            <span className={styles.summaryMeta}>覆盖协作权限、模型入口、安全凭证与操作追踪</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>视觉基线</span>
            <span className={styles.summaryValue}>1</span>
            <span className={styles.summaryMeta}>统一遵循全局主题 token、状态徽标与深海控制台样式</span>
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionHeaderStack}>
            <h2 className={styles.sectionTitle}>设置模块</h2>
            <p className={styles.sectionDescription}>
              选择要继续维护的模块。入口会根据当前角色自动过滤不可访问的内容。
            </p>
          </div>
        </div>

        {visibleCards.length > 0 ? (
          <div className={styles.linkGrid}>
            {visibleCards.map((card) => {
              const Icon = card.icon;

              return (
                <Link key={card.href} href={card.href} className={styles.linkCard}>
                  <div className={styles.linkCardIcon}>
                    <Icon size={22} strokeWidth={1.8} />
                  </div>
                  <div className={styles.linkCardBody}>
                    <div className={styles.itemNameRow}>
                      <span className={styles.linkCardTitle}>{card.title}</span>
                      <span className={`${styles.pill} ${styles.info}`}>{card.metric}</span>
                    </div>
                    <div className={styles.linkCardText}>{card.description}</div>
                  </div>
                </Link>
              );
            })}
          </div>
        ) : (
          <div className={styles.empty}>
            <div className={styles.emptyTitle}>当前角色没有可访问的设置模块</div>
            <div className={styles.emptyText}>
              如需查看成员、模型、密钥或审计信息，请联系管理员为当前账号授予对应权限。
            </div>
          </div>
        )}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionHeaderStack}>
            <h2 className={styles.sectionTitle}>本组基线</h2>
            <p className={styles.sectionDescription}>
              当前设置页组已统一接入全局主题架构，避免继续在子页内部重复定义背景、色值和状态语义。
            </p>
          </div>
        </div>

        <div className={styles.card}>
          <div className={styles.itemLead}>
            <div className={styles.moduleIcon}>
              <Settings2 size={22} strokeWidth={1.8} />
            </div>
            <div className={styles.itemInfo}>
              <div className={styles.itemName}>统一设计架构</div>
              <div className={styles.itemMeta}>
                Design Token 分层、CSS Variables、data-theme 切换和控制台共享组件语义已经在这组页面内落地。
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
