import { expect, type Page, test } from '@playwright/test';

const email = process.env.E2E_TEST_EMAIL || 'e2e-owner@example.com';
const password = process.env.E2E_TEST_PASSWORD || 'E2ePassword123!';

const seededRuns = {
  running: '00000000-0000-4000-8000-000000000101',
  paused: '00000000-0000-4000-8000-000000000102',
  gate: '00000000-0000-4000-8000-000000000103',
};

async function login(page: Page) {
  await page.goto('/login');

  await expect(page.getByRole('heading', { name: '登录控制台' })).toBeVisible();
  await page.getByLabel('电子邮箱').fill(email);
  await page.getByLabel('登录密码').fill(password);
  await page.getByRole('button', { name: '登录控制台' }).click();

  await expect(page).toHaveURL(/\/console/);
}

test('PR E2E 覆盖登录、Agent 运行台、详情页、暂停恢复和 Gate 审批', async ({ page }) => {
  await login(page);

  await page.goto('/console/agents');
  await expect(page.getByRole('heading', { name: '目标驱动的长程任务运行台' })).toBeVisible();
  await expect(page.getByRole('region', { name: '启动自主 Agent' })).toBeVisible();

  const createdGoal = `E2E 浏览器启动 Agent ${Date.now()}`;
  await page.getByPlaceholder('输入需要自主规划和长程执行的目标').fill(createdGoal);
  await page.getByRole('button', { name: '启动 Agent' }).click();
  await expect(page.getByTestId('agent-run-list')).toContainText(createdGoal, { timeout: 15_000 });

  await page.goto(`/console/agents/${seededRuns.running}`);
  await expect(page.getByTestId('agent-run-status')).toHaveText('执行中');
  await expect(page.getByRole('heading', { name: '动态计划图' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '执行步骤' })).toBeVisible();
  await page.getByRole('button', { name: '暂停' }).click();
  await expect(page.getByTestId('agent-run-status')).toHaveText('已暂停');

  await page.goto(`/console/agents/${seededRuns.paused}`);
  await expect(page.getByTestId('agent-run-status')).toHaveText('已暂停');
  await page.getByRole('button', { name: '继续执行' }).click();
  await expect(page.getByTestId('agent-run-status')).not.toHaveText('已暂停');
  await expect(page.getByText('继续执行失败')).toBeHidden();

  await page.goto(`/console/agents/${seededRuns.gate}`);
  await expect(page.getByTestId('agent-run-status')).toHaveText('等待 Gate');
  await expect(page.getByTestId('agent-gate-panel')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Gate 审批' })).toBeVisible();
  await page.getByRole('button', { name: '批准继续' }).click();
  await expect(page.getByTestId('agent-gate-panel')).toBeHidden();
  await expect(page.getByTestId('agent-run-status')).not.toHaveText('等待 Gate');
  await expect(page.getByText('Gate 审批失败')).toBeHidden();
});
