-- 003: 成员关系唯一性约束
-- 目标：防止同一用户在同一工作空间内被并发写入重复成员关系。

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM memberships
        GROUP BY user_id, workspace_id
        HAVING COUNT(*) > 1
    ) THEN
        CREATE UNIQUE INDEX IF NOT EXISTS uq_membership_user_workspace
            ON memberships (user_id, workspace_id);
    END IF;
END $$;

COMMIT;
