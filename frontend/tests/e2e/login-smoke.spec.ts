import { expect, test } from '@playwright/test';

test('登录页展示关键认证入口', async ({ page }) => {
  await page.goto('/login');

  await expect(page.getByRole('heading', { name: '登录控制台' })).toBeVisible();
  await expect(page.getByLabel('电子邮箱')).toBeVisible();
  await expect(page.getByLabel('登录密码')).toBeVisible();
  await expect(page.getByRole('button', { name: '登录控制台' })).toBeVisible();
});
