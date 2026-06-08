import { redirect } from 'next/navigation';

export default function ProjectsRedirectPage() {
  // 保留 Issue #20 指定的顶层入口，实际体验复用控制台内容项目列表。
  redirect('/console/projects');
}
