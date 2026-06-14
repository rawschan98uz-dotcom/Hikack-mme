import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, '..', 'captured');
const PHONE = process.env.MODME_PHONE;
const PASSWORD = process.env.MODME_PASSWORD;
const BASE = process.env.MODME_BASE_URL || 'https://ravvatech188.modme.uz';

if (!PHONE || !PASSWORD) {
  console.error('Set MODME_PHONE and MODME_PASSWORD env vars');
  process.exit(1);
}

fs.mkdirSync(path.join(OUT, 'screenshots'), { recursive: true });
fs.mkdirSync(path.join(OUT, 'network'), { recursive: true });

const networkLog = [];

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'ru-RU',
  });
  const page = await context.newPage();

  page.on('request', (req) => {
    const url = req.url();
    if (
      url.includes('/api/') ||
      url.includes('/v1/') ||
      url.includes('/v2/')
    ) {
      networkLog.push({
        type: 'request',
        method: req.method(),
        url: url.split('?')[0],
        resourceType: req.resourceType(),
      });
    }
  });

  page.on('response', (res) => {
    const url = res.url();
    if (
      url.includes('/api/') ||
      url.includes('/v1/') ||
      url.includes('/v2/')
    ) {
      // Log endpoint patterns only — never store auth response bodies.
      networkLog.push({
        type: 'response',
        status: res.status(),
        url: url.split('?')[0],
      });
    }
  });

  console.log('Opening login page...');
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.waitForFunction(
    () => !document.querySelector('.loading') || document.querySelectorAll('input').length > 0,
    { timeout: 90000 }
  );
  await page.waitForTimeout(3000);

  await page.screenshot({
    path: path.join(OUT, 'screenshots', '01-login-page.png'),
    fullPage: true,
  });

  const inputs = await page.locator('input:visible').all();
  console.log(`Found ${inputs.length} visible inputs`);

  // ModMe login: phone + password
  const phoneInput = page.locator('input[type="tel"], input[type="text"], input[name*="phone"], input[placeholder*="phone" i], input[placeholder*="тел" i]').first();
  const passInput = page.locator('input[type="password"]').first();

  if ((await phoneInput.count()) > 0) {
    await phoneInput.fill(PHONE);
  } else if (inputs.length >= 1) {
    await inputs[0].fill(PHONE);
  }

  if ((await passInput.count()) > 0) {
    await passInput.fill(PASSWORD);
  } else if (inputs.length >= 2) {
    await inputs[1].fill(PASSWORD);
  }

  await page.screenshot({
    path: path.join(OUT, 'screenshots', '02-login-filled.png'),
    fullPage: true,
  });

  const submit = page.locator(
    'button[type="submit"], button:has-text("Войти"), button:has-text("Kirish"), button:has-text("Login"), button:has-text("Sign")'
  ).first();

  if ((await submit.count()) > 0) {
    await submit.click();
  } else {
    await page.keyboard.press('Enter');
  }

  await page.waitForTimeout(5000);
  try {
    await page.waitForURL('**/dashboard/**', { timeout: 30000 });
  } catch {
    console.log('Dashboard URL not reached, current:', page.url());
  }

  await page.waitForTimeout(3000);
  await page.screenshot({
    path: path.join(OUT, 'screenshots', '03-after-login.png'),
    fullPage: true,
  });

  // Navigate dashboard
  await page.goto(`${BASE}/dashboard/default`, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForTimeout(3000);
  await page.screenshot({
    path: path.join(OUT, 'screenshots', '04-dashboard-default.png'),
    fullPage: true,
  });

  // Collect nav links
  const links = await page.locator('a[href]').evaluateAll((els) =>
    els.map((el) => ({
      text: (el.textContent || '').trim().slice(0, 80),
      href: el.getAttribute('href'),
    }))
  );

  const uniqueLinks = [...new Map(links.filter((l) => l.href).map((l) => [l.href, l])).values()];

  // Sidebar / menu items
  const menuItems = await page.locator('nav a, .sidebar a, [class*="menu"] a, [class*="nav"] a').evaluateAll((els) =>
    els.map((el) => ({
      text: (el.textContent || '').trim().slice(0, 80),
      href: el.getAttribute('href'),
    }))
  );

  const pageInfo = {
    url: page.url(),
    title: await page.title(),
    capturedAt: new Date().toISOString(),
    links: uniqueLinks.slice(0, 200),
    menuItems: [...new Map(menuItems.filter((m) => m.href).map((m) => [m.href, m])).values()],
  };

  fs.writeFileSync(path.join(OUT, 'dashboard-structure.json'), JSON.stringify(pageInfo, null, 2));

  // Accessibility tree (Playwright aria snapshot)
  try {
    const aria = await page.locator('body').ariaSnapshot();
    fs.writeFileSync(path.join(OUT, 'dashboard-a11y.txt'), aria);
  } catch {
    /* optional */
  }

  fs.writeFileSync(path.join(OUT, 'network', 'api-calls.json'), JSON.stringify(networkLog, null, 2));

  // Extract routes from page HTML
  const html = await page.content();
  fs.writeFileSync(path.join(OUT, 'pages', 'dashboard-logged-in.html'), html);

  console.log('Done. URL:', page.url());
  console.log('Network entries:', networkLog.length);
  console.log('Menu items:', pageInfo.menuItems.length);

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
