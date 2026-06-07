'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, BookOpenText, Clapperboard, FileText, Megaphone } from 'lucide-react';

import { scenarioApi, type ScenarioTemplate } from '@/lib/api';
import styles from '../projects/scenario-workbench.module.css';

const scenarioIcons: Record<string, typeof BookOpenText> = {
  novel_writing: BookOpenText,
  marketing_copy: Megaphone,
  short_video_script: Clapperboard,
  prd: FileText,
};

export default function ScenariosPage() {
  const [scenarios, setScenarios] = useState<ScenarioTemplate[]>([]);
  const [selectedCode, setSelectedCode] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const response = await scenarioApi.listScenarios();
        if (active) {
          setScenarios(response.scenarios);
          setSelectedCode(response.scenarios[0]?.code || '');
        }
      } catch (requestError) {
        if (active) {
          setError(requestError instanceof Error ? requestError.message : '场景模板加载失败');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, []);

  const selectedScenario = scenarios.find((scenario) => scenario.code === selectedCode);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCode || !title.trim() || creating) {
      return;
    }
    setCreating(true);
    setError('');
    try {
      const project = await scenarioApi.createProject({
        scenario_code: selectedCode,
        title: title.trim(),
        description: description.trim() || null,
      });
      window.location.href = `/console/projects/${project.id}`;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '创建内容项目失败');
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>场景模板</span>
          <h1 className={styles.title}>选择商业场景，创建可持续运营的内容项目</h1>
          <p className={styles.subtitle}>
            每个场景都绑定输入表单、生成模式、资产类型和检查规则。项目会沉淀长期记忆，运行记录仍保留 Trace、Artifact 与重跑能力。
          </p>
          <div className={styles.actions}>
            <Link href="/console/projects" className={styles.secondaryButton}>
              查看内容项目
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>
        </div>
        <div className={styles.heroMetric}>
          <span>可用场景</span>
          <strong>{scenarios.length}</strong>
          <p className={styles.cardText}>小说作为深度样板，营销、短视频和 PRD 提供商业内容扩展底座。</p>
        </div>
      </section>

      {error ? <div className={styles.errorBanner}>{error}</div> : null}
      {loading ? <div className={styles.loading}>正在加载场景模板...</div> : null}

      <section className={styles.grid}>
        {scenarios.map((scenario) => {
          const Icon = scenarioIcons[scenario.code] || FileText;
          const assetTypes = scenario.artifact_schema.asset_types || [];
          return (
            <article key={scenario.code} className={styles.card}>
              <div className={styles.cardHeader}>
                <span className={styles.badge}>{scenario.category}</span>
                <Icon size={22} aria-hidden="true" />
              </div>
              <div>
                <h2 className={styles.cardTitle}>{scenario.name}</h2>
                <p className={styles.cardText}>{scenario.description}</p>
              </div>
              <div className={styles.assetMeta}>
                <span className={styles.badge}>{scenario.default_generation_modes.length} 个生成模式</span>
                <span className={styles.badge}>{assetTypes.length} 类资产</span>
              </div>
              <button
                className={scenario.code === selectedCode ? styles.button : styles.secondaryButton}
                type="button"
                onClick={() => setSelectedCode(scenario.code)}
              >
                选择场景
              </button>
            </article>
          );
        })}
      </section>

      <form className={styles.formPanel} onSubmit={handleCreate}>
        <div className={styles.panelHeader}>
          <div>
            <h2 className={styles.panelTitle}>创建内容项目</h2>
            <p className={styles.metaText}>
              当前选择：{selectedScenario?.name || '请选择场景'}
            </p>
          </div>
          <button className={styles.button} type="submit" disabled={!title.trim() || creating}>
            {creating ? '创建中...' : '创建项目'}
          </button>
        </div>
        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>项目名称</span>
            <input
              className={styles.input}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="例如：雾城手记第一季"
            />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>场景代码</span>
            <select
              className={styles.select}
              value={selectedCode}
              onChange={(event) => setSelectedCode(event.target.value)}
            >
              {scenarios.map((scenario) => (
                <option key={scenario.code} value={scenario.code}>
                  {scenario.name}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.fullField}>
            <span className={styles.fieldLabel}>项目说明</span>
            <textarea
              className={styles.textarea}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="补充项目目标、受众、风格或长期约束"
            />
          </label>
        </div>
      </form>
    </div>
  );
}
