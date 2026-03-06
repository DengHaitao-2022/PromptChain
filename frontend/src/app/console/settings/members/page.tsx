'use client';

/**
 * 成员管理页面
 */

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import styles from '../settings.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

interface Member {
    id: string;
    user_id: string;
    email: string;
    display_name: string | null;
    avatar_url: string | null;
    role: string;
    joined_at: string;
}

export default function MembersPage() {
    const { workspace, hasPermission } = useAuth();
    const [members, setMembers] = useState<Member[]>([]);
    const [loading, setLoading] = useState(true);
    const [inviteEmail, setInviteEmail] = useState('');
    const [inviteRole, setInviteRole] = useState('viewer');
    const [inviting, setInviting] = useState(false);

    useEffect(() => {
        if (workspace) {
            fetchMembers();
        }
    }, [workspace]);

    async function fetchMembers() {
        try {
            const response = await fetch(`${API_BASE}/workspaces/${workspace?.id}/members`, {
                credentials: 'include',
            });
            if (response.ok) {
                const data = await response.json();
                setMembers(data.members || []);
            }
        } catch (err) {
            console.error('加载成员失败', err);
        } finally {
            setLoading(false);
        }
    }

    async function handleInvite() {
        if (!inviteEmail) return;
        setInviting(true);
        try {
            const response = await fetch(`${API_BASE}/workspaces/${workspace?.id}/invite`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
            });
            if (response.ok) {
                setInviteEmail('');
                alert('邀请已发送');
            } else {
                const error = await response.json();
                alert(error.detail || '邀请失败');
            }
        } catch (err) {
            alert('邀请失败');
        } finally {
            setInviting(false);
        }
    }

    const roleLabels: Record<string, string> = {
        owner: '拥有者',
        admin: '管理员',
        editor: '编辑者',
        viewer: '查看者',
    };

    return (
        <div className={styles.container}>
            <h1 className={styles.title}>成员管理</h1>
            <p className={styles.subtitle}>管理工作空间成员和权限</p>

            {hasPermission('member', 'manage') && (
                <div className={styles.section}>
                    <h2 className={styles.sectionTitle}>邀请成员</h2>
                    <div className={styles.inviteForm}>
                        <input
                            type="email"
                            placeholder="输入邮箱地址"
                            value={inviteEmail}
                            onChange={(e) => setInviteEmail(e.target.value)}
                            className={styles.input}
                        />
                        <select
                            value={inviteRole}
                            onChange={(e) => setInviteRole(e.target.value)}
                            className={styles.select}
                        >
                            <option value="viewer">查看者</option>
                            <option value="editor">编辑者</option>
                            <option value="admin">管理员</option>
                        </select>
                        <button
                            onClick={handleInvite}
                            disabled={inviting || !inviteEmail}
                            className={styles.button}
                        >
                            {inviting ? '发送中...' : '发送邀请'}
                        </button>
                    </div>
                </div>
            )}

            <div className={styles.section}>
                <h2 className={styles.sectionTitle}>成员列表</h2>
                {loading ? (
                    <div className={styles.loading}><div className={styles.spinner} /></div>
                ) : (
                    <div className={styles.list}>
                        {members.map((member) => (
                            <div key={member.id} className={styles.listItem}>
                                <div className={styles.avatar}>
                                    {member.display_name?.[0] || member.email[0]}
                                </div>
                                <div className={styles.itemInfo}>
                                    <div className={styles.itemName}>{member.display_name || member.email}</div>
                                    <div className={styles.itemMeta}>{member.email}</div>
                                </div>
                                <div className={styles.itemRole}>
                                    <span className={`${styles.roleTag} ${styles[member.role]}`}>
                                        {roleLabels[member.role] || member.role}
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
