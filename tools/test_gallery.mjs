import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, extname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, expect } from '@playwright/test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../docs');
const catalog = JSON.parse(await readFile(join(root, 'data/posters.json'), 'utf8'));
const artifactDir = await mkdtemp(join(tmpdir(), 'exhibition-gallery-'));
const prefix = '/virtual-exhibition/';
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' };
const server = createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    if (!pathname.startsWith(prefix)) { response.writeHead(404).end(); return; }
    const path = resolve(root, pathname.slice(prefix.length) || 'index.html');
    if (!path.startsWith(root + sep)) { response.writeHead(403).end(); return; }
    const data = await readFile(path);
    response.writeHead(200, { 'Content-Type': mime[extname(path)] || 'application/octet-stream' });
    response.end(data);
  } catch { response.writeHead(404).end(); }
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const url = `http://127.0.0.1:${server.address().port}${prefix}`;
let browser;
try {
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined });
  const context = await browser.newContext({ viewport: { width: 1396, height: 1127 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const exceptions = [];
  const requests = [];
  page.on('pageerror', (error) => exceptions.push(error.message));
  page.on('request', (request) => requests.push(request.url()));
  await page.goto(url);
  await expect(page.locator('.poster-card')).toHaveCount(catalog.posters.length);
  await expect(page.locator('#poster-count')).toHaveText(`Toutes les affiches (${catalog.posters.length})`);
  assert.deepEqual(await page.locator('.poster-title').allTextContents(), catalog.posters.map((p) => p.metadata.title));
  await expect(page.locator('.poster-image img')).toHaveCount(catalog.posters.length);
  await page.waitForFunction(() => [...document.querySelectorAll('.poster-image img')].every((image) => image.complete && image.naturalWidth > 0));
  assert.equal(await page.locator('#poster-grid').evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(' ').length), 5);
  assert(!requests.some((value) => value.includes('/detail/')), 'Detail images must not load before opening a poster');
  assert(requests.every((value) => value.startsWith(url)), 'No third-party or origin-root requests');
  await page.screenshot({ path: join(artifactDir, 'desktop.png'), fullPage: true });

  for (const label of ['Le projet']) {
    const link = page.getByRole('link', { name: label, exact: true });
    await expect(link).toHaveAttribute('aria-disabled', 'true');
    assert.equal(await link.getAttribute('href'), null);
    await link.evaluate((el) => el.click());
    await link.focus();
    await page.keyboard.press('Enter');
    assert.equal(page.url(), url);
  }
  await expect(page.getByRole('link', { name: 'La halle 3D', exact: true })).toHaveAttribute('href', './halle.html');
  await expect(page.getByRole('link', { name: /Entrer dans la halle/ })).toHaveAttribute('href', './halle.html');
  assert(!requests.some((value) => value.includes('/vendor/three/') || value.includes('/models/')), 'The 2D page must not load the 3D engine or assets');

  const first = page.locator('.poster-link').first();
  await first.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#poster-dialog')).toBeVisible();
  await expect(page.locator('#detail-image')).toBeVisible();
  await expect(page.locator('#detail-title')).toHaveText(catalog.posters[0].metadata.title);
  await page.locator('#zoom-button').click();
  await expect(page.locator('#zoom-button')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#zoom-button').click();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('#detail-title')).toHaveText(catalog.posters[1].metadata.title);
  await page.keyboard.press('Escape');
  await expect(page.locator('#poster-dialog')).not.toBeVisible();
  await expect(first).toBeFocused();

  await page.locator('#sort-button').click();
  const collator = new Intl.Collator('fr', { numeric: true, sensitivity: 'base' });
  const sorted = catalog.posters.map((poster) => poster.metadata.title).sort(collator.compare);
  assert.deepEqual(await page.locator('.poster-title').allTextContents(), sorted);
  await page.locator('#sort-button').click();
  assert.deepEqual(await page.locator('.poster-title').allTextContents(), [...sorted].reverse());

  const unknown = catalog.posters.find((poster) => !poster.metadata.author);
  if (unknown) {
    await page.goto(`${url}#poster=${unknown.id}`);
    await expect(page.locator('#detail-title')).toHaveText(unknown.metadata.title);
    await expect(page.locator('#detail-author')).toBeHidden();
    await expect(page.locator('#detail-year')).toBeHidden();
    await page.locator('#close-dialog').click();
  }

  await page.goto(url);
  await expect(page.locator('.poster-card')).toHaveCount(catalog.posters.length);
  await page.locator('.poster-link').first().click();
  await expect(page.locator('#poster-dialog')).toBeVisible();
  await page.goBack();
  await expect(page.locator('#poster-dialog')).not.toBeVisible();
  await page.goForward();
  await expect(page.locator('#poster-dialog')).toBeVisible();
  await page.locator('#close-dialog').click();

  for (const width of [320, 390, 768, 1024]) {
    await page.setViewportSize({ width, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Overflow at ${width}px`);
    if (width === 390) {
      await page.screenshot({ path: join(artifactDir, 'mobile.png'), fullPage: true });
      await page.locator('.poster-link').first().click();
      await expect(page.locator('#detail-image')).toBeVisible();
      await expect(page.locator('#close-dialog')).toBeInViewport();
      await page.screenshot({ path: join(artifactDir, 'mobile-detail.png') });
      await page.locator('#close-dialog').click();
    }
  }

  await page.route('**/data/posters.json', (route) => route.fulfill({ status: 503, body: 'Unavailable' }));
  await page.reload();
  await expect(page.locator('#gallery-error')).toBeVisible();
  await page.unroute('**/data/posters.json');
  await page.locator('#retry-button').click();
  await expect(page.locator('.poster-card')).toHaveCount(catalog.posters.length);
  await expect(page.locator('#gallery-error')).toBeHidden();

  await page.route('**/data/posters.json', (route) => route.fulfill({ json: { schema_version: 2, posters: [] } }));
  await page.reload();
  await expect(page.locator('#gallery-status')).toHaveText('Les affiches seront bientôt disponibles.');
  await expect(page.locator('#sort-button')).toBeDisabled();
  assert.deepEqual(exceptions, [], 'No uncaught JavaScript errors');
  console.log(`PASS: ${catalog.posters.length} posters; responsive layout; inactive navigation; sorting; detail/zoom/keyboard/focus; deep links/history; error retry; empty state; repository prefix.`);
  console.log(`Screenshots: ${artifactDir}`);
} finally {
  await browser?.close();
  await new Promise((done) => server.close(done));
}
