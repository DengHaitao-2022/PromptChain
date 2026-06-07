import { redirect } from 'next/navigation';

interface ProjectRunsRedirectPageProps {
  params: Promise<{ id: string }>;
}

export default async function ProjectRunsRedirectPage({ params }: ProjectRunsRedirectPageProps) {
  const { id } = await params;
  // 运行记录子入口深链到同一个项目工作台运行记录视图。
  redirect(`/console/projects/${id}?tab=runs`);
}
