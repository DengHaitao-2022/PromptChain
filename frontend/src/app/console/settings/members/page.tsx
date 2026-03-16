'use client';

/**
 * 成员管理页面
 */

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import {
  Role,
  WorkspaceMember,
  WorkspaceAccessStatus,
  getRoleLabel,
  inviteWorkspaceMember,
  listWorkspaceMembers,
  removeWorkspaceMember,
  updateWorkspaceMemberAccess,
  updateWorkspaceMemberRole,
} from '@/lib/auth';
import styles from '../settings.module.css';

const MANAGEABLE_ROLES: Exclude<Role, 'owner'>[] = ['viewer', 'editor', 'admin'];

function getWorkspaceAccessLabel(status: WorkspaceMember['workspace_access']) {
  if (status === 'suspended') {
    return '访问已暂停';
  }
  return '可访问';
}

function getWorkspaceAccessTone(status: WorkspaceMember['workspace_access']) {
  return status === 'suspended' ? styles.error : styles.success;
}

function getAccountStatusLabel(status: WorkspaceMember['account_status']) {
  if (status === 'active') {
    return '账号正常';
  }
  if (status === 'suspended') {
    return '全局账号已停用';
  }
  return '账号未激活';
}

function getAccountStatusTone(status: WorkspaceMember['account_status']) {
  if (status === 'active') {
    return styles.success;
  }
  if (status === 'suspended') {
    return styles.error;
  }
  return styles.warning;
}

export default function MembersPage() {
  const { user, workspace, hasPermission } = useAuth();
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<Exclude<Role, 'owner'>>('viewer');
  const [inviting, setInviting] = useState(false);
  const [pendingMembershipId, setPendingMembershipId] = useState<string | null>(null);
  const [pendingUserId, setPendingUserId] = useState<string | null>(null);
  const [roleDrafts, setRoleDrafts] = useState<Record<string, Exclude<Role, 'owner'>>>({});

  const canReadMembers = hasPermission('member', 'read');
  const canManageMembers = hasPermission('member', 'manage');

  const fetchMembers = useCallback(async () => {
    if (!workspace || !canReadMembers) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError('');

    try {
      const data = await listWorkspaceMembers(workspace.id);
      setMembers(data);
      setRoleDrafts(
        Object.fromEntries(
          data
            .filter((member) => member.role !== 'owner')
            .map((member) => [member.id, member.role as Exclude<Role, 'owner'>]),
        ),
      );
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : '加载成员失败');
    } finally {
      setLoading(false);
    }
  }, [workspace, canReadMembers]);

  useEffect(() => {
    void fetchMembers();
  }, [fetchMembers]);

  const sortedMembers = useMemo(() => {
    const roleOrder: Role[] = ['owner', 'admin', 'editor', 'viewer'];
    return [...members].sort((left, right) => {
      const accessDelta =
        Number(left.workspace_access === 'suspended') - Number(right.workspace_access === 'suspended');
      if (accessDelta !== 0) {
        return accessDelta;
      }
      const roleDelta = roleOrder.indexOf(left.role) - roleOrder.indexOf(right.role);
      if (roleDelta !== 0) {
        return roleDelta;
      }
      return left.email.localeCompare(right.email);
    });
  }, [members]);

  const summary = useMemo(() => {
    const total = members.length;
    const activeAccess = members.filter((member) => member.workspace_access === 'active').length;
    const suspendedAccess = members.filter((member) => member.workspace_access === 'suspended').length;
    const unverified = members.filter((member) => !member.email_verified).length;

    return { total, activeAccess, suspendedAccess, unverified };
  }, [members]);

  async function handleInvite() {
    if (!workspace || !inviteEmail.trim()) {
      return;
    }

    setInviting(true);
    setFeedback('');
    setError('');

    try {
      const result = await inviteWorkspaceMember(workspace.id, {
        email: inviteEmail.trim(),
        role: inviteRole,
      });
      setInviteEmail('');
      setInviteRole('viewer');
      setFeedback(result.message || '邀请已发送');
    } catch (inviteError) {
      setError(inviteError instanceof Error ? inviteError.message : '邀请失败');
    } finally {
      setInviting(false);
    }
  }

  async function handleRoleUpdate(member: WorkspaceMember) {
    const nextRole = roleDrafts[member.id];
    if (!nextRole || nextRole === member.role) {
      return;
    }

    setPendingMembershipId(member.id);
    setFeedback('');
    setError('');

    try {
      const result = await updateWorkspaceMemberRole(member.id, nextRole);
      setFeedback(result.message || '成员角色已更新');
      await fetchMembers();
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : '更新角色失败');
    } finally {
      setPendingMembershipId(null);
    }
  }

  async function handleRemoveMember(member: WorkspaceMember) {
    const confirmed = window.confirm(`确认将 ${member.display_name || member.email} 移出当前工作空间吗？`);
    if (!confirmed) {
      return;
    }

    setPendingMembershipId(member.id);
    setFeedback('');
    setError('');

    try {
      const result = await removeWorkspaceMember(member.id);
      setFeedback(result.message || '成员已移除');
      await fetchMembers();
    } catch (removeError) {
      setError(removeError instanceof Error ? removeError.message : '移除成员失败');
    } finally {
      setPendingMembershipId(null);
    }
  }

  async function handleToggleWorkspaceAccess(member: WorkspaceMember) {
    const nextStatus: WorkspaceAccessStatus =
      member.workspace_access === 'suspended' ? 'active' : 'suspended';
    const confirmed = window.confirm(
      nextStatus === 'active'
        ? `确认恢复 ${member.display_name || member.email} 在当前工作空间的访问权限吗？\n\n此操作不会修改其全局账号状态。`
        : `确认暂停 ${member.display_name || member.email} 在当前工作空间的访问权限吗？\n\n此操作不会修改其全局账号状态，也不会影响其他工作空间。`,
    );
    if (!confirmed) {
      return;
    }

    setPendingUserId(member.user_id);
    setFeedback('');
    setError('');

    try {
      const result = await updateWorkspaceMemberAccess(member.user_id, nextStatus);
      setFeedback(result.message || '工作空间访问状态已更新');
      await fetchMembers();
    } catch (statusError) {
      setError(statusError instanceof Error ? statusError.message : '更新工作空间访问状态失败');
    } finally {
      setPendingUserId(null);
    }
  }

  if (!canReadMembers) {
    return (
      <div className={styles.container}>
        <section className={styles.hero}>
          <div className={styles.heroContent}>
            <span className={styles.eyebrow}>Workspace Access</span>
            <h1 className={styles.title}>成员管理</h1>
            <p className={styles.subtitle}>
              您当前没有查看成员列表的权限。如需继续，请联系工作空间管理员调整角色。
            </p>
          </div>
          <div className={styles.heroActions}>
            <Link href="/console" className={`${styles.button} ${styles.buttonSecondary}`}>
              返回控制台首页
            </Link>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <span className={styles.eyebrow}>Workspace Access</span>
          <h1 className={styles.title}>成员管理</h1>
          <p className={styles.subtitle}>
            管理成员角色、当前工作空间访问边界与邀请节奏，不会修改用户的全局账号状态。
          </p>
        </div>

        <div className={styles.heroActions}>
          <button
            className={`${styles.button} ${styles.buttonSecondary}`}
            onClick={() => void fetchMembers()}
            type="button"
          >
            <RefreshCw size={16} strokeWidth={2} />
            刷新列表
          </button>
        </div>

        <div className={styles.summaryGrid}>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>成员总数</span>
            <span className={styles.summaryValue}>{summary.total}</span>
            <span className={styles.summaryMeta}>当前工作空间：{workspace?.name || '未选择'}</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>可访问</span>
            <span className={styles.summaryValue}>{summary.activeAccess}</span>
            <span className={styles.summaryMeta}>可以正常进入并操作当前工作空间</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>已暂停</span>
            <span className={styles.summaryValue}>{summary.suspendedAccess}</span>
            <span className={styles.summaryMeta}>仅暂停当前工作空间访问，不影响其他工作空间</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryLabel}>待验证邮箱</span>
            <span className={styles.summaryValue}>{summary.unverified}</span>
            <span className={styles.summaryMeta}>可用于识别尚未完成初次验证的成员</span>
          </div>
        </div>
      </section>

      {feedback ? (
        <div className={`${styles.notice} ${styles.noticeSuccess}`} role="status">
          {feedback}
        </div>
      ) : null}

      {error ? (
        <div className={`${styles.notice} ${styles.noticeError}`} role="alert">
          {error}
        </div>
      ) : null}

      {canManageMembers ? (
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div className={styles.sectionHeaderStack}>
              <h2 className={styles.sectionTitle}>邀请成员</h2>
              <p className={styles.sectionDescription}>
                新成员会继承当前工作空间角色，后续仍可单独调整为查看者、编辑者或管理员。
              </p>
            </div>
          </div>

          <div className={styles.inviteForm}>
            <input
              type="email"
              placeholder="输入成员邮箱地址"
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
              className={styles.input}
            />
            <select
              value={inviteRole}
              onChange={(event) => setInviteRole(event.target.value as Exclude<Role, 'owner'>)}
              className={styles.select}
            >
              <option value="viewer">查看者</option>
              <option value="editor">编辑者</option>
              <option value="admin">管理员</option>
            </select>
            <button
              onClick={() => void handleInvite()}
              disabled={inviting || !inviteEmail.trim()}
              className={styles.button}
              type="button"
            >
              {inviting ? '发送中...' : '发送邀请'}
            </button>
          </div>
          <p className={styles.helperText}>
            邀请邮件由后端服务发送；若成员已存在于系统中，将直接收到当前工作空间邀请。
          </p>
        </section>
      ) : null}

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div className={styles.sectionHeaderStack}>
            <h2 className={styles.sectionTitle}>成员列表</h2>
            <p className={styles.sectionDescription}>
              “暂停访问”仅阻止该成员进入当前工作空间；“移除成员”会直接移出当前工作空间。
            </p>
          </div>
          <div className={styles.sectionActions}>
            <button
              className={`${styles.button} ${styles.buttonGhost}`}
              onClick={() => void fetchMembers()}
              type="button"
            >
              <RefreshCw size={16} strokeWidth={2} />
              刷新
            </button>
          </div>
        </div>

        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
          </div>
        ) : sortedMembers.length === 0 ? (
          <div className={styles.empty}>
            <div className={styles.emptyTitle}>当前工作空间还没有成员</div>
            <div className={styles.emptyText}>先发送邀请，再按角色和访问边界整理协作关系。</div>
          </div>
        ) : (
          <div className={styles.list}>
            {sortedMembers.map((member) => {
              const isOwner = member.role === 'owner';
              const isCurrentUser = member.user_id === user?.id;
              const roleDraft = roleDrafts[member.id] || 'viewer';
              const isRoleSaving = pendingMembershipId === member.id;
              const isStatusSaving = pendingUserId === member.user_id;

              return (
                <article key={member.id} className={styles.listItem}>
                  <div className={styles.itemLead}>
                    <div className={styles.avatar}>{member.display_name?.[0] || member.email[0]}</div>
                    <div className={styles.itemInfo}>
                      <div className={styles.itemNameRow}>
                        <span className={styles.itemName}>{member.display_name || member.email}</span>
                        {isCurrentUser ? <span className={styles.currentUserTag}>当前账号</span> : null}
                      </div>
                      <div className={styles.itemMeta}>{member.email}</div>
                      <div className={styles.badgeRow}>
                        <span className={`${styles.roleTag} ${styles[member.role]}`}>
                          {getRoleLabel(member.role)}
                        </span>
                        <span
                          className={`${styles.statusTag} ${getWorkspaceAccessTone(member.workspace_access)}`}
                        >
                          {getWorkspaceAccessLabel(member.workspace_access)}
                        </span>
                        <span
                          className={`${styles.statusTag} ${getAccountStatusTone(member.account_status)}`}
                        >
                          {getAccountStatusLabel(member.account_status)}
                        </span>
                        {!member.email_verified ? (
                          <span className={`${styles.statusTag} ${styles.warning}`}>邮箱未验证</span>
                        ) : null}
                      </div>
                      <div className={styles.itemMetaMuted}>
                        加入时间：{new Date(member.joined_at).toLocaleDateString('zh-CN')}
                      </div>
                    </div>
                  </div>

                  {canManageMembers ? (
                    <div className={styles.actionPanel}>
                      <div className={styles.actionsRow}>
                        <select
                          value={roleDraft}
                          onChange={(event) =>
                            setRoleDrafts((current) => ({
                              ...current,
                              [member.id]: event.target.value as Exclude<Role, 'owner'>,
                            }))
                          }
                          className={styles.select}
                          disabled={isOwner || isCurrentUser || isRoleSaving || isStatusSaving}
                        >
                          {MANAGEABLE_ROLES.map((role) => (
                            <option key={role} value={role}>
                              {getRoleLabel(role)}
                            </option>
                          ))}
                        </select>
                        <button
                          className={`${styles.button} ${styles.buttonSmall}`}
                          disabled={isOwner || isCurrentUser || isRoleSaving || isStatusSaving || roleDraft === member.role}
                          onClick={() => void handleRoleUpdate(member)}
                          type="button"
                        >
                          {isRoleSaving ? '保存中...' : '保存角色'}
                        </button>
                      </div>

                      <div className={styles.actionsRow}>
                        <button
                          className={`${styles.button} ${styles.buttonSmall} ${
                            member.workspace_access === 'suspended' ? '' : styles.buttonDanger
                          }`}
                          disabled={isOwner || isCurrentUser || isStatusSaving}
                          onClick={() => void handleToggleWorkspaceAccess(member)}
                          type="button"
                        >
                          {isStatusSaving ? '处理中...' : member.workspace_access === 'suspended' ? '恢复访问' : '暂停访问'}
                        </button>
                        <button
                          className={`${styles.button} ${styles.buttonSmall} ${styles.buttonGhost}`}
                          disabled={isOwner || isCurrentUser || isRoleSaving || isStatusSaving}
                          onClick={() => void handleRemoveMember(member)}
                          type="button"
                        >
                          移除成员
                        </button>
                      </div>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
