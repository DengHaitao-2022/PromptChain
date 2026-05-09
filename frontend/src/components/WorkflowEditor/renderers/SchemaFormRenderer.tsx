/**
 * 属性面板表单渲染器
 * 为什么这样分层：基于 Zod schema 动态推导出表单项。
 * 完全隔离 UI 组件与具体节点的业务数据，只需配置 schema 即可生成交互组件。
 */

'use client';

import React, { useEffect, useMemo, useRef } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z, ZodEnum, ZodNumber, ZodString, ZodDefault, ZodOptional } from 'zod';
import styles from '../panels/PanelStyles.module.css';

interface SchemaFormRendererProps {
    schema: z.ZodTypeAny;
    defaultValues: Record<string, unknown>;
    onChange: (data: Record<string, unknown>) => void;
}

// 解析可选的或带默认值的 Zod 类型，找到真实底层类型
function getInnerZodType(schema: z.ZodTypeAny): z.ZodTypeAny {
    let current: any = schema;
    while (current instanceof ZodDefault || current instanceof ZodOptional) {
        current = current._def.innerType;
    }
    return current as z.ZodTypeAny;
}

export default function SchemaFormRenderer({ schema, defaultValues, onChange }: SchemaFormRendererProps) {
    const { control, watch, formState: { errors } } = useForm({
        resolver: zodResolver(schema as any),
        defaultValues,
        mode: 'onChange' // 边填边校验，并在 UI 上及时反馈错误
    });

    // 监控表单所有值变化并触发外部 onChange
    const formValues = watch();
    const prevValuesRef = useRef<string | undefined>(undefined);

    useEffect(() => {
        // 如果当前有错误，可以选择不向上传递，或者由上层决定如何处理
        // 为了方便自动保存，还是把最新值传上去
        const currentStr = JSON.stringify(formValues);
        if (currentStr !== prevValuesRef.current) {
            prevValuesRef.current = currentStr;
            onChange(formValues);
        }
    }, [formValues, onChange]);

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
                                            // TODO: 这里如果要在 Zod 中带中文 label 可以借助自定义元数据
                                            // 目前为了最简使用原英文值，或者外部映射
                                            let optLabel = opt;
                                            if (opt === 'gpt-4o') optLabel = 'GPT-4o';
                                            if (opt === 'gpt-4o-mini') optLabel = 'GPT-4o Mini';
                                            if (opt === 'claude-3.5-sonnet') optLabel = 'Claude 3.5 Sonnet';
                                            if (opt === 'gemini-2.0-flash') optLabel = 'Gemini 2.0 Flash';
                                            if (opt === 'approval') optLabel = '审批';
                                            if (opt === 'edit') optLabel = '编辑';
                                            if (opt === 'input') optLabel = '输入';
                                            if (opt === 'text') optLabel = '纯文本';
                                            if (opt === 'markdown') optLabel = 'Markdown';
                                            if (opt === 'json') optLabel = 'JSON';
                                            return <option key={opt} value={opt}>{optLabel}</option>;
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
