import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile, mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, extname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, expect } from '@playwright/test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../docs');
const catalog = JSON.parse(await readFile(join(root, 'data/posters.json'), 'utf8'));
const artifacts = await mkdtemp(join(tmpdir(), 'exhibition-instagram-'));
const prefix = '/virtual-exhibition/';
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' };
const server = createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    if (!pathname.startsWith(prefix)) throw new Error();
    const path = resolve(root, pathname.slice(prefix.length) || 'index.html');
    if (!path.startsWith(root + sep)) throw new Error();
    response.writeHead(200, { 'Content-Type': mime[extname(path)] || 'application/octet-stream' }).end(await readFile(path));
  } catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const base = `http://127.0.0.1:${server.address().port}${prefix}`;
let browser;
try {
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined });
  const page = await browser.newPage({ viewport: { width: 1396, height: 1050 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  // Known random input tests a shuffled traversal without a probabilistic assertion.
  await page.addInitScript(() => { Math.random = () => .37; });
  await page.goto(base + 'instagram.html');
  const next = page.locator('#next-post');
  const imageButton = page.locator('#post-image-button');
  await expect(next).toBeEnabled();
  const ids = [];
  for (let i = 0; i < catalog.posters.length; i += 1) {
    await expect(page.locator('#post-image')).toBeVisible();
    await page.waitForFunction(() => document.querySelector('#post-image').naturalWidth > 0);
    const id = await imageButton.getAttribute('data-poster-id');
    ids.push(id);
    const poster = catalog.posters.find(item => item.id === id);
    assert(poster);
    await expect(page.locator('#post-title')).toHaveText(poster.metadata.title || 'Affiche sans titre');
    await expect(page.locator('#post-author')).toHaveText(poster.metadata.author || 'Auteurice non renseigné·e');
    await expect(page.locator('#feed-position')).toHaveText(`Affiche ${i + 1} sur ${catalog.posters.length} · Ordre aléatoire`);
    if (i < catalog.posters.length - 1) await (i % 2 ? next : imageButton).click();
  }
  assert.equal(new Set(ids).size, catalog.posters.length, 'Each poster appears once per cycle');
  assert.notDeepEqual(ids, catalog.posters.map(p => p.id), 'Traversal shuffles catalogue order');
  await next.focus();
  await page.keyboard.press('Enter');
  assert.notEqual(await imageButton.getAttribute('data-poster-id'), ids.at(-1));
  await expect(page.locator('#feed-position')).toContainText(`Affiche 1 sur ${catalog.posters.length}`);
  await imageButton.focus();
  const before = await imageButton.getAttribute('data-poster-id');
  await page.keyboard.press('Space');
  assert.notEqual(await imageButton.getAttribute('data-poster-id'), before);
  for (const width of [1396, 1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 1050 });
    await expect(page.locator('#post-image')).toBeVisible();
    const layout = await page.evaluate(() => {
      const screen = document.querySelector('.phone-screen').getBoundingClientRect();
      const button = document.querySelector('#post-image-button').getBoundingClientRect();
      const caption = document.querySelector('.post-caption').getBoundingClientRect();
      return { overflow: document.documentElement.scrollWidth > innerWidth, imageHeight: button.height, captionFits: caption.bottom <= screen.bottom, fit: getComputedStyle(document.querySelector('#post-image')).objectFit };
    });
    assert(!layout.overflow && layout.captionFits && layout.imageHeight > 100 && layout.fit === 'contain', JSON.stringify({ width, ...layout }));
    if ([1396, 390, 320].includes(width)) await page.screenshot({ path: join(artifacts, `feed-${width}.png`), fullPage: true });
  }
  // Fetch failure and recovery, malformed and empty catalogues.
  await page.route('**/data/posters.json', route => route.fulfill({ status: 503, body: 'Unavailable' }));
  await page.reload();
  await expect(page.locator('#feed-error')).toBeVisible();
  await expect(next).toBeDisabled();
  await page.unroute('**/data/posters.json');
  await page.locator('#retry-feed').click();
  await expect(next).toBeEnabled();
  for (const data of [{ schema_version: 2, posters: [] }, { schema_version: 2, posters: [{ id: 'bad' }] }]) {
    await page.route('**/data/posters.json', route => route.fulfill({ json: data }));
    await page.reload();
    await expect(page.locator('#feed-error')).toBeVisible();
    await page.unroute('**/data/posters.json');
  }
  // A broken image keeps the traversal available.
  await page.route('**/posters/texture/**', route => route.abort());
  await page.reload();
  await expect(page.locator('#image-status')).toContainText('Image indisponible');
  await expect(next).toBeEnabled();
  await next.click();
  await expect(page.locator('#feed-position')).toContainText('Affiche 2 sur');
  await page.unroute('**/posters/texture/**');
  // All pages link to the new view, including on a GitHub Pages subpath.
  for (const filename of ['index.html', 'halle.html', 'instagram.html']) {
    const html = await (await page.request.get(base + filename)).text();
    assert(html.includes('href="./instagram.html"'));
  }
  assert.deepEqual(errors, []);
  console.log(`Instagram checks passed: ${catalog.posters.length} posters, shuffled cycle, captions, keyboard, responsive layout and error recovery. Screenshots: ${artifacts}`);
} finally {
  await browser?.close();
  await new Promise(done => server.close(done));
}
