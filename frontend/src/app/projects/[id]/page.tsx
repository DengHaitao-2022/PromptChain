import { redirect } from 'next/navigation';

interface ProjectRedirectPageProps {
  params: Promise<{ id: string }>;
}

export default async function ProjectRedirectPage({ params }: ProjectRedirectPageProps) {
  const { id } = await params;
  // 顶层项目详情入口只负责路由兼容，避免复制一套项目工作台 UI。
  redirect(`/console/projects/${id}`);
}
