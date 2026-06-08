import { redirect } from 'next/navigation';

export default function ScenariosRedirectPage() {
  // 保留 Issue #20 指定的顶层入口，实际体验复用控制台场景工作台。
  redirect('/console/scenarios');
}
