import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
for (const [path, name] of [['/', 'home'], ['/login', 'login'], ['/signup', 'signup']]) {
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto('http://localhost:4173' + path, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `scripts/tmp-shot-${name}.png` });
  console.log(name, 'ok', errors);
}
await browser.close();
