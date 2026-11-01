import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, extname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, expect } from '@playwright/test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../docs');
const catalog = JSON.parse(await readFile(join(root, 'data/posters.json'), 'utf8'));
const artifacts = await mkdtemp(join(tmpdir(), 'exhibition-hall-'));
console.log(`Screenshots: ${artifacts}`);
const prefix = '/virtual-exhibition/';
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml' };
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
const base = `http://127.0.0.1:${server.address().port}${prefix}`;
let browser;
try {
  browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const exceptions = [], errors = [], requests = [];
  page.on('pageerror', (error) => exceptions.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('request', (request) => requests.push(request.url()));
  const diagnostic = () => page.evaluate(async () => (await import('./js/hall.js')).getDiagnostics());
  await page.goto(`${base}halle.html`);
  await expect(page.locator('#hall-stage')).toHaveAttribute('data-state', 'complete', { timeout: 45000 });
  const stats = await diagnostic();
  console.log('Scene:', stats);
  assert.equal(stats.parts, 5);
  assert.equal(stats.posters, catalog.posters.length);
  assert.equal(stats.garageMaterials, 1);
  assert.equal(stats.sharedSurface, true);
  assert.equal(stats.aoChannel, 1);
  assert.equal(stats.aoMeshes, 5);
  assert(stats.triangles > 10000, 'Real garage geometry rendered');
  for (const texture of ['albedo.webp', 'normal.webp', 'surface.webp', 'ao.webp']) {
    assert.equal(requests.filter((url) => new URL(url).pathname.endsWith(texture)).length, 1, `One shared request for ${texture}`);
  }
  assert(requests.every((url) => url.startsWith(base)), 'All runtime assets are hosted under the repository prefix');
  assert(!requests.some((url) => url.includes('/posters/detail/')), 'No full-resolution reading images in 3D');
  await page.screenshot({ path: join(artifacts, 'overview.png'), fullPage: true });
  // Same scene/camera with a neutral AO texture for visual comparison.
  const neutralAO = await context.newPage();
  await neutralAO.route('**/ao.webp?*', (route) => route.fulfill({
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC', 'base64'),
  }));
  await neutralAO.goto(`${base}halle.html`);
  await expect(neutralAO.locator('#hall-stage')).toHaveAttribute('data-state', 'complete', { timeout: 45000 });
  await neutralAO.screenshot({ path: join(artifacts, 'overview-without-ao.png'), fullPage: true });
  await neutralAO.close();
  await page.locator('#hall-next').click();
  await expect(page.locator('#hall-title')).toHaveText(catalog.posters[0].metadata.title);
  await expect(page.locator('#hall-read')).toHaveAttribute('href', `./index.html#poster=${catalog.posters[0].id}`);
  await expect.poll(async () => (await diagnostic()).highResolutionPosterTextures).toBe(1);
  await page.screenshot({ path: join(artifacts, 'poster.png'), fullPage: true });
  const before = (await diagnostic()).camera;
  await page.locator('#hall-canvas').focus();
  await page.keyboard.down('z');
  await page.waitForTimeout(400);
  await page.keyboard.up('z');
  assert.notDeepEqual((await diagnostic()).camera, before, 'Keyboard movement changes position');
  const unknown = catalog.posters.findIndex((poster) => !poster.metadata.author);
  if (unknown >= 0) {
    await page.locator('#hall-select').selectOption(String(unknown));
    await expect(page.locator('#hall-author')).toBeHidden();
  }
  await page.locator('#hall-overview').click();
  await expect(page.locator('#hall-title')).toHaveText('Le garage');
  await expect(page.locator('#hall-read')).toBeHidden();
  assert.equal((await diagnostic()).highResolutionPosterTextures, 0);
  assert.deepEqual(exceptions, []);
  assert.deepEqual(errors, []);

  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.locator('#hall-next').click();
  await expect(page.locator('#hall-title')).toHaveText(catalog.posters[0].metadata.title);
  await page.screenshot({ path: join(artifacts, 'mobile.png'), fullPage: true });

  await page.goto(`${base}halle.html#poster=${catalog.posters[2].id}`);
  await expect(page.locator('#hall-title')).toHaveText(catalog.posters[2].metadata.title, { timeout: 30000 });
  await expect(page.locator('#hall-stage')).toHaveAttribute('data-state', 'complete', { timeout: 30000 });

  // The early scene remains usable while secondary model parts are still pending.
  let release;
  const gate = new Promise((done) => { release = done; });
  await page.route('**/garage-e.glb?*', async (route) => { await gate; await route.continue(); });
  await page.goto(`${base}halle.html`);
  await expect(page.locator('#hall-stage')).toHaveAttribute('data-state', 'ready', { timeout: 30000 });
  await expect(page.locator('#hall-next')).toBeEnabled();
  assert((await diagnostic()).parts < 5);
  release();
  await expect(page.locator('#hall-stage')).toHaveAttribute('data-state', 'complete', { timeout: 30000 });
  await page.unroute('**/garage-e.glb?*');

  const fallback = await context.newPage();
  await fallback.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
      return type.startsWith('webgl') ? null : original.call(this, type, ...rest);
    };
  });
  await fallback.goto(`${base}halle.html`);
  await expect(fallback.locator('#hall-error')).toBeVisible();
  await expect(fallback.getByRole('link', { name: 'Voir les affiches en 2D', exact: true })).toHaveAttribute('href', './index.html');
  await fallback.close();
  console.log('PASS: real WebGL garage; 5 parts; single shared material/atlas; progressive opening; poster navigation, keyboard movement, resolution eviction; mobile; deep links; no-WebGL fallback.');
} finally {
  await browser?.close();
  await new Promise((done) => server.close(done));
}
