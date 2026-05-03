-- 002: 审计日志持久化追踪字段升级
-- 目标：为 audit_logs 补齐结构化事件、请求链路、快照和查询索引。

BEGIN;

ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS event_id VARCHAR(64);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS request_id VARCHAR(64);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS trace_id VARCHAR(64);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS span_id VARCHAR(32);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS event_category VARCHAR(50);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS event_type VARCHAR(50);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS outcome VARCHAR(20);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS actor_snapshot JSON DEFAULT '{}'::json;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS target_snapshot JSON DEFAULT '{}'::json;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS metadata_json JSON DEFAULT '{}'::json;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS schema_version VARCHAR(20) DEFAULT 'legacy';

-- 历史记录补齐稳定事件 ID 和默认结果，保证旧日志也能被追溯和分页展示。
UPDATE audit_logs
SET event_id = id
WHERE event_id IS NULL;

UPDATE audit_logs
SET outcome = 'success'
WHERE outcome IS NULL;

UPDATE audit_logs
SET schema_version = 'legacy'
WHERE schema_version IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ix_audit_logs_event_id
    ON audit_logs (event_id)
    WHERE event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_audit_logs_request_id
    ON audit_logs (request_id);

CREATE INDEX IF NOT EXISTS ix_audit_logs_trace_id
    ON audit_logs (trace_id);

CREATE INDEX IF NOT EXISTS ix_audit_logs_outcome
    ON audit_logs (outcome);

CREATE INDEX IF NOT EXISTS ix_audit_logs_target
    ON audit_logs (target_type, target_id);

COMMIT;
