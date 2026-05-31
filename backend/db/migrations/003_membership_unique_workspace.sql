-- 003: 成员关系唯一性约束
-- 目标：防止同一用户在同一工作空间内被并发写入重复成员关系。

BEGIN;

DO $$
BEGIN
    WITH ranked_memberships AS (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY user_id, workspace_id
                ORDER BY joined_at NULLS LAST, id
            ) AS row_number
        FROM memberships
    )
    DELETE FROM memberships
    USING ranked_memberships
    WHERE memberships.id = ranked_memberships.id
      AND ranked_memberships.row_number > 1;

    CREATE UNIQUE INDEX IF NOT EXISTS uq_membership_user_workspace
        ON memberships (user_id, workspace_id);
END $$;

COMMIT;
