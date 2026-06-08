'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Layers3, LibraryBig, Plus, Search } from 'lucide-react';

import { scenarioApi, type ContentProject, type ScenarioTemplate } from '@/lib/api';
import { formatAppDateTime } from '@/lib/date-time';
import styles from './scenario-workbench.module.css';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ContentProject[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioTemplate[]>([]);
  const [scenarioFilter, setScenarioFilter] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const [projectResponse, scenarioResponse] = await Promise.all([
          scenarioApi.listProjects(),
          scenarioApi.listScenarios(),
        ]);
        if (active) {
          setProjects(projectResponse.projects);
          setScenarios(scenarioResponse.scenarios);
        }
      } catch (requestError) {
        if (active) {
          setError(requestError instanceof Error ? requestError.message : '内容项目加载失败');
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

  const scenarioByCode = useMemo(
    () => new Map(scenarios.map((scenario) => [scenario.code, scenario])),
    [scenarios],
  );
  const filteredProjects = projects.filter((project) => {
    if (scenarioFilter && project.scenario_code !== scenarioFilter) {
      return false;
    }
    const text = `${project.title} ${project.description || ''}`.toLowerCase();
    return text.includes(query.trim().toLowerCase());
  });
  const activeProjects = projects.filter((project) => project.status === 'active').length;

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>内容项目</span>
          <h1 className={styles.title}>用项目承载场景记忆、资产和运行记录</h1>
          <p className={styles.subtitle}>
            内容项目把 Story Bible、品牌语气、脚本资产和 PRD 约束沉淀为长期上下文，让每次工作流运行不再孤立。
          </p>
          <div className={styles.actions}>
            <Link href="/console/scenarios" className={styles.button}>
              <Plus size={16} aria-hidden="true" />
              新建项目
            </Link>
          </div>
        </div>
        <div className={styles.heroMetric}>
          <span>活跃项目</span>
          <strong>{activeProjects}</strong>
          <p className={styles.cardText}>项目运行可继续跳转到现有工作流详情页，保留 Trace、Artifact 与节点重跑。</p>
        </div>
      </section>

      <section className={styles.toolbar}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>搜索项目</span>
          <span className={styles.inlineActions}>
            <Search size={16} aria-hidden="true" />
            <input
              className={styles.input}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="输入项目名称或说明"
            />
          </span>
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>场景筛选</span>
          <select
            className={styles.select}
            value={scenarioFilter}
            onChange={(event) => setScenarioFilter(event.target.value)}
          >
            <option value="">全部场景</option>
            {scenarios.map((scenario) => (
              <option key={scenario.code} value={scenario.code}>
                {scenario.name}
              </option>
            ))}
          </select>
        </label>
      </section>

      {error ? <div className={styles.errorBanner}>{error}</div> : null}
      {loading ? <div className={styles.loading}>正在加载内容项目...</div> : null}

      {!loading && filteredProjects.length === 0 ? (
        <div className={styles.emptyState}>
          <LibraryBig size={34} aria-hidden="true" />
          <p>还没有符合条件的内容项目。</p>
          <Link href="/console/scenarios" className={styles.secondaryButton}>
            选择场景创建
          </Link>
        </div>
      ) : null}

      <section className={styles.grid}>
        {filteredProjects.map((project) => {
          const scenario = scenarioByCode.get(project.scenario_code);
          return (
            <article key={project.id} className={styles.card}>
              <div className={styles.cardHeader}>
                <span className={styles.badge}>{scenario?.name || project.scenario_code}</span>
                <Layers3 size={22} aria-hidden="true" />
              </div>
              <div>
                <h2 className={styles.cardTitle}>{project.title}</h2>
                <p className={styles.cardText}>{project.description || '暂无项目说明。'}</p>
              </div>
              <div className={styles.assetMeta}>
                <span className={styles.badge}>{project.status === 'active' ? '活跃' : '归档'}</span>
                <span className={styles.badge}>更新于 {formatAppDateTime(project.updated_at)}</span>
              </div>
              <Link href={`/console/projects/${project.id}`} className={styles.linkButton}>
                进入工作台
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </article>
          );
        })}
      </section>
    </div>
  );
}
