import { redirect } from 'next/navigation';

interface ProjectAssetsRedirectPageProps {
  params: Promise<{ id: string }>;
}

export default async function ProjectAssetsRedirectPage({ params }: ProjectAssetsRedirectPageProps) {
  const { id } = await params;
  // 资产子入口深链到同一个项目工作台资产视图。
  redirect(`/console/projects/${id}?tab=assets`);
}
