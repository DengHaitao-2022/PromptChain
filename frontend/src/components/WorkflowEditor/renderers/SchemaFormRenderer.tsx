/**
 * 属性面板表单渲染器
 * 为什么这样分层：基于 Zod schema 动态推导出表单项。
 * 完全隔离 UI 组件与具体节点的业务数据，只需配置 schema 即可生成交互组件。
 */

'use client';

import React, { useEffect, useMemo, useRef } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z, ZodBoolean, ZodDefault, ZodEnum, ZodNumber, ZodOptional, ZodRecord } from 'zod';
import styles from '../panels/PanelStyles.module.css';

type ZodResolverSchema = Parameters<typeof zodResolver>[0];

interface SchemaFormRendererProps {
    schema: z.ZodTypeAny;
    defaultValues: Record<string, unknown>;
    onChange: (data: Record<string, unknown>) => void;
}

// 解析可选的或带默认值的 Zod 类型，找到真实底层类型
function getInnerZodType(schema: z.ZodTypeAny): z.ZodTypeAny {
    let current: z.ZodTypeAny = schema;
    while (current instanceof ZodDefault || current instanceof ZodOptional) {
        current = (
            current as z.ZodDefault<z.ZodTypeAny> | z.ZodOptional<z.ZodTypeAny>
        )._def.innerType;
    }
    return current;
}

function formatJsonInput(value: unknown): string {
    if (typeof value === 'string') {
        return value;
    }
    try {
        return JSON.stringify(value ?? {}, null, 2);
    } catch {
        return '{}';
    }
}

function parseJsonInput(value: string): unknown {
    try {
        return JSON.parse(value);
    } catch {
        return value;
    }
}

function enumOptionLabel(opt: string): string {
    const labels: Record<string, string> = {
        'gpt-4o': 'GPT-4o',
        'gpt-4o-mini': 'GPT-4o Mini',
        'claude-3.5-sonnet': 'Claude 3.5 Sonnet',
        'gemini-2.0-flash': 'Gemini 2.0 Flash',
        approval: '审批',
        edit: '编辑',
        input: '输入',
        text: '纯文本',
        markdown: 'Markdown',
        json: 'JSON',
        pre_outline: '提纲前',
        post_content: '正文后',
        pre_finalize: '收尾前',
        policy_default: '按策略',
        auto: '自动执行',
        gate_required: '强制 Gate',
        terminate: '终止',
        skip: '跳过',
        retry: '重试',
        enter_gate: '进入 Gate',
        'artifact.read': '读取 Artifact',
        'artifact.write': '写入 Artifact',
        'artifact.list_versions': '列出 Artifact 版本',
        'retrieval.query_workspace_knowledge': '检索工作空间知识库',
        'document.load_text': '载入文本',
        'document.chunk_text': '文本切块',
        'validation.json_schema_validate': 'JSON Schema 校验',
        'content.outline_consistency_check': '提纲一致性检查',
        'content.style_check': '内容风格检查',
        'fact.check_claims': '事实声明初筛',
    };
    return labels[opt] ?? opt;
}

export default function SchemaFormRenderer({ schema, defaultValues, onChange }: SchemaFormRendererProps) {
    const { control, getValues, watch, formState: { errors } } = useForm({
        resolver: zodResolver(schema as ZodResolverSchema),
        defaultValues,
        mode: 'onChange' // 边填边校验，并在 UI 上及时反馈错误
    });

    // 监控表单所有值变化并触发外部 onChange
    const prevValuesRef = useRef<string | undefined>(undefined);
    const onChangeRef = useRef(onChange);

    useEffect(() => {
        onChangeRef.current = onChange;
    }, [onChange]);

    useEffect(() => {
        const notifyChange = (values: Record<string, unknown>) => {
            const currentStr = JSON.stringify(values);
            if (currentStr !== prevValuesRef.current) {
                prevValuesRef.current = currentStr;
                onChangeRef.current(values);
            }
        };

        // 如果当前有错误，可以选择不向上传递，或者由上层决定如何处理
        // 为了方便自动保存，还是把最新值传上去
        notifyChange(getValues());

        // 使用 watch 回调订阅值变化，避免依赖不存在的 subscribe API。
        const subscription = watch((values) => {
            notifyChange(values as Record<string, unknown>);
        });

        return () => subscription.unsubscribe();
    }, [getValues, watch]);

    // 从 Zod Object schema 中解析字段进行渲染
    const fields = useMemo(() => {
        if (schema instanceof z.ZodObject) {
            const shape = schema.shape;
            return Object.entries(shape).map(([key, fieldSchema]) => {
                const fieldAny = fieldSchema as z.ZodTypeAny;
                const description = fieldAny.description || key;
                const innerType = getInnerZodType(fieldAny);

                return {
                    key,
                    label: description,
                    type: innerType,
                };
            });
        }
        return [];
    }, [schema]);

    if (fields.length === 0) {
        return <div className={styles.emptyForm}>无可用配置项</div>;
    }

    return (
        <form className={styles.schemaForm}>
            {fields.map(({ key, label, type }) => {
                const errorMsg = errors[key]?.message as string | undefined;

                return (
                    <div key={key} className={styles.configSection}>
                        <label className={styles.configLabel}>{label}</label>

                        {type instanceof ZodEnum ? (
                            <Controller
                                name={key}
                                control={control}
                                render={({ field }) => (
                                    <select {...field} className={styles.configSelect}>
                                        {(type.options as string[]).map(opt => {
                                            return <option key={opt} value={opt}>{enumOptionLabel(opt)}</option>;
                                        })}
                                    </select>
                                )}
                            />
                        ) : type instanceof ZodNumber ? (
                            <Controller
                                name={key}
                                control={control}
                                render={({ field }) => {
                                    // 对于 threshold 我们知道它的范围和 step
                                    const isDecimal = key.toLowerCase().includes('threshold');
                                    return (
                                        <input
                                            type="number"
                                            step={isDecimal ? "0.05" : "1"}
                                            min={isDecimal ? "0" : undefined}
                                            max={isDecimal ? "1" : undefined}
                                            {...field}
                                            onChange={e => field.onChange(parseFloat(e.target.value))}
                                            className={styles.configInput}
                                        />
                                    );
                                }}
                            />
                        ) : type instanceof ZodRecord || type instanceof z.ZodObject ? (
                            <Controller
                                name={key}
                                control={control}
                                render={({ field }) => (
                                    <textarea
                                        value={formatJsonInput(field.value)}
                                        onChange={event => field.onChange(parseJsonInput(event.target.value))}
                                        className={styles.configTextarea}
                                        rows={6}
                                        spellCheck={false}
                                    />
                                )}
                            />
                        ) : type instanceof ZodBoolean ? (
                            <Controller
                                name={key}
                                control={control}
                                render={({ field }) => (
                                    <label className={styles.configCheckbox}>
                                        <input
                                            type="checkbox"
                                            checked={Boolean(field.value)}
                                            onChange={event => field.onChange(event.target.checked)}
                                        />
                                        <span>启用</span>
                                    </label>
                                )}
                            />
                        ) : (
                            <Controller
                                name={key}
                                control={control}
                                render={({ field }) => (
                                    <input
                                        type="text"
                                        {...field}
                                        className={styles.configInput}
                                    />
                                )}
                            />
                        )}

                        {errorMsg && <span className={styles.fieldError}>{errorMsg}</span>}
                    </div>
                );
            })}
        </form>
    );
}
