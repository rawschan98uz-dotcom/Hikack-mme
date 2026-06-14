import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, '..', 'captured', 'sections');
const PHONE = process.env.MODME_PHONE;
const PASSWORD = process.env.MODME_PASSWORD;
const BASE = process.env.MODME_BASE_URL || 'https://ravvatech188.modme.uz';

const ROUTES = [
  '/dashboard/default',
  '/leads',
  '/teachers',
  '/groups',
  '/students',
  '/students/list?statuses=5',
  '/students/debtors',
  '/reminders',
  '/rating',
  '/attendance-reports',
  '/finance/payments',
  '/finance/withdraw',
  '/finance/cost',
  '/finance/new-salaries',
  '/reports/conversion',
  '/reports/attendance',
  '/reports/leads',
  '/courses',
  '/rooms',
  '/holiday',
  '/settings',
  '/staff/list',
  '/billing',
  '/archive/list',
  '/sms',
  '/call',
  '/history/logs',
  '/auto-sms',
  '/tags',
  '/form',
];

if (!PHONE || !PASSWORD) {
  console.error('Set MODME_PHONE and MODME_PASSWORD');
  process.exit(1);
}

fs.mkdirSync(OUT, { recursive: true });

function slug(route) {
  return route.replace(/^\//, '').replace(/[/?=&]/g, '_') || 'root';
}

async function login(page) {
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.waitForFunction(
    () => !document.querySelector('.loading') || document.querySelectorAll('input').length > 0,
    { timeout: 90000 },
  );
  await page.waitForTimeout(2000);
  const phoneInput = page.locator('input[type="tel"], input[type="text"]').first();
  const passInput = page.locator('input[type="password"]').first();
  await phoneInput.fill(PHONE);
  await passInput.fill(PASSWORD);
  const submit = page.locator('button[type="submit"]').first();
  if ((await submit.count()) > 0) await submit.click();
  else await page.keyboard.press('Enter');
  await page.waitForTimeout(5000);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const apiByRoute = {};

  page.on('request', (req) => {
    const url = req.url();
    if (url.includes('api.modme.uz')) {
      const key = page.__currentRoute || 'unknown';
      if (!apiByRoute[key]) apiByRoute[key] = new Set();
      apiByRoute[key].add(`${req.method()} ${url.split('?')[0]}`);
    }
  });

  await login(page);

  const report = [];

  for (const route of ROUTES) {
    page.__currentRoute = route;
    const name = slug(route);
    console.log('Visiting', route);

    try {
      await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle', timeout: 60000 });
      await page.waitForTimeout(2500);

      await page.screenshot({
        path: path.join(OUT, `${name}.png`),
        fullPage: true,
      });

      const headings = await page.locator('h1, h2, h3, .page-title, [class*="title"]').evaluateAll((els) =>
        els.map((el) => (el.textContent || '').trim()).filter(Boolean).slice(0, 10),
      );

      const buttons = await page.locator('button').evaluateAll((els) =>
        els.map((el) => (el.textContent || '').trim()).filter((t) => t.length > 0 && t.length < 60).slice(0, 20),
      );

      const tableHeaders = await page.locator('th, [role="columnheader"]').evaluateAll((els) =>
        [...new Set(els.map((el) => (el.textContent || '').trim()).filter(Boolean))],
      );

      const tabs = await page.locator('[role="tab"], .nav-tabs a, .tab').evaluateAll((els) =>
        els.map((el) => (el.textContent || '').trim()).filter(Boolean).slice(0, 15),
      );

      report.push({
        route,
        url: page.url(),
        title: await page.title(),
        headings: [...new Set(headings.flat())],
        buttons: [...new Set(buttons.flat())],
        tableHeaders,
        tabs: [...new Set(tabs.flat())],
        apis: [...(apiByRoute[route] || [])].sort(),
      });
    } catch (err) {
      report.push({ route, error: String(err) });
    }
  }

  fs.writeFileSync(path.join(OUT, 'sections-report.json'), JSON.stringify(report, null, 2));
  console.log('Captured', report.length, 'sections ->', OUT);

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
