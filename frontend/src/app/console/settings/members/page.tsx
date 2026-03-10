'use client';

/**
 * 成员管理页面
 */

import { useEffect, useMemo, useState } from 'react';
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

function getAccountStatusLabel(status: WorkspaceMember['account_status']) {
  if (status === 'active') {
    return '账号正常';
  }
  if (status === 'suspended') {
    return '全局账号已停用';
  }
  return '账号未激活';
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

  async function fetchMembers() {
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
  }

  useEffect(() => {
    void fetchMembers();
  }, [workspace?.id, canReadMembers]);

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
        <h1 className={styles.title}>成员管理</h1>
        <p className={styles.subtitle}>暂无访问权限</p>
        <div className={styles.empty}>
          <p>您当前没有查看成员列表的权限。</p>
          <p style={{ fontSize: 14, marginTop: 8 }}>如需访问，请联系工作空间管理员调整角色。</p>
          <a href="/console" className={styles.button} style={{ marginTop: 16, display: 'inline-flex' }}>
            返回控制台首页
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <h1 className={styles.title}>成员管理</h1>
      <p className={styles.subtitle}>管理成员角色与当前工作空间访问边界，不会修改用户全局账号状态。</p>

      {feedback && (
        <div
          style={{
            marginBottom: 16,
            padding: '12px 14px',
            borderRadius: 10,
            background: '#ecfdf5',
            color: '#166534',
            fontSize: 14,
          }}
        >
          {feedback}
        </div>
      )}

      {error && (
        <div
          style={{
            marginBottom: 16,
            padding: '12px 14px',
            borderRadius: 10,
            background: '#fef2f2',
            color: '#b91c1c',
            fontSize: 14,
          }}
        >
          {error}
        </div>
      )}

      {canManageMembers && (
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>邀请成员</h2>
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
            <button onClick={() => void handleInvite()} disabled={inviting || !inviteEmail.trim()} className={styles.button} type="button">
              {inviting ? '发送中...' : '发送邀请'}
            </button>
          </div>
        </div>
      )}

      <div className={styles.section}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            marginBottom: 16,
          }}
        >
          <div>
            <h2 className={styles.sectionTitle} style={{ marginBottom: 4 }}>
              成员列表
            </h2>
            <p style={{ margin: 0, color: '#6b7280', fontSize: 13 }}>
              当前工作空间：{workspace?.name || '未选择'}
            </p>
            <p style={{ margin: '6px 0 0', color: '#9ca3af', fontSize: 12 }}>
              “暂停访问”仅阻止该成员进入当前工作空间；“移除成员”会直接移出当前工作空间。
            </p>
          </div>
          <button className={styles.button} onClick={() => void fetchMembers()} type="button">
            刷新列表
          </button>
        </div>

        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
          </div>
        ) : sortedMembers.length === 0 ? (
          <div className={styles.card}>
            <p style={{ margin: 0, color: '#6b7280' }}>当前工作空间还没有成员。</p>
          </div>
        ) : (
          <div className={styles.list}>
            {sortedMembers.map((member) => {
              const isOwner = member.role === 'owner';
              const isCurrentUser = member.user_id === user?.id;
              const roleDraft = roleDrafts[member.id] || 'viewer';
              const isRoleSaving = pendingMembershipId === member.id;
              const isStatusSaving = pendingUserId === member.user_id;
              const workspaceAccessLabel = getWorkspaceAccessLabel(member.workspace_access);
              const accountStatusLabel = getAccountStatusLabel(member.account_status);

              return (
                <div
                  key={member.id}
                  className={styles.listItem}
                  style={{
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                  }}
                >
                  <div style={{ display: 'flex', gap: 16, flex: '1 1 280px' }}>
                    <div className={styles.avatar}>{member.display_name?.[0] || member.email[0]}</div>
                    <div className={styles.itemInfo}>
                      <div className={styles.itemName}>
                        {member.display_name || member.email}
                        {isCurrentUser && (
                          <span style={{ marginLeft: 8, fontSize: 12, color: '#6366f1' }}>当前账号</span>
                        )}
                      </div>
                      <div className={styles.itemMeta}>{member.email}</div>
                      <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <span className={`${styles.roleTag} ${styles[member.role]}`}>{getRoleLabel(member.role)}</span>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '4px 12px',
                            borderRadius: 20,
                            fontSize: 12,
                            fontWeight: 500,
                            background: member.workspace_access === 'active' ? '#ecfdf5' : '#fef2f2',
                            color: member.workspace_access === 'active' ? '#166534' : '#b91c1c',
                          }}
                        >
                          {workspaceAccessLabel}
                        </span>
                        {member.account_status !== 'active' && (
                          <span
                            style={{
                              display: 'inline-block',
                              padding: '4px 12px',
                              borderRadius: 20,
                              fontSize: 12,
                              fontWeight: 500,
                              background: '#eef2ff',
                              color: '#4338ca',
                            }}
                          >
                            {accountStatusLabel}
                          </span>
                        )}
                        {!member.email_verified && (
                          <span
                            style={{
                              display: 'inline-block',
                              padding: '4px 12px',
                              borderRadius: 20,
                              fontSize: 12,
                              fontWeight: 500,
                              background: '#fff7ed',
                              color: '#c2410c',
                            }}
                          >
                            邮箱未验证
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {canManageMembers && (
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 10,
                        minWidth: 240,
                        flex: '0 0 240px',
                      }}
                    >
                      <div style={{ display: 'flex', gap: 8 }}>
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
                          style={{ flex: 1 }}
                        >
                          {MANAGEABLE_ROLES.map((role) => (
                            <option key={role} value={role}>
                              {getRoleLabel(role)}
                            </option>
                          ))}
                        </select>
                        <button
                          className={styles.button}
                          disabled={isOwner || isCurrentUser || isRoleSaving || isStatusSaving || roleDraft === member.role}
                          onClick={() => void handleRoleUpdate(member)}
                          type="button"
                        >
                          {isRoleSaving ? '保存中...' : '保存角色'}
                        </button>
                      </div>

                      <div style={{ display: 'flex', gap: 8 }}>
                        <button
                          className={styles.button}
                          disabled={isOwner || isCurrentUser || isStatusSaving}
                          onClick={() => void handleToggleWorkspaceAccess(member)}
                          type="button"
                          style={{
                            flex: 1,
                            background: member.workspace_access === 'suspended' ? '#059669' : '#b91c1c',
                          }}
                        >
                          {isStatusSaving ? '处理中...' : member.workspace_access === 'suspended' ? '恢复访问' : '暂停访问'}
                        </button>
                        <button
                          className={styles.button}
                          disabled={isOwner || isCurrentUser || isRoleSaving || isStatusSaving}
                          onClick={() => void handleRemoveMember(member)}
                          type="button"
                          style={{ flex: 1, background: '#374151' }}
                        >
                          移除成员
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
