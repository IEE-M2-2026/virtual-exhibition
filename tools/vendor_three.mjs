import { build } from 'esbuild';
import { readFile, mkdir, copyFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const source = new URL('./node_modules/three/', import.meta.url);
const target = new URL('../docs/vendor/three/', import.meta.url);
const metadata = JSON.parse(await readFile(new URL('package.json', source)));
await mkdir(new URL('build/', target), { recursive: true });
await mkdir(new URL('addons/loaders/', target), { recursive: true });
for (const [input, output] of [
  ['build/three.module.js', 'build/three.module.min.js'],
  ['examples/jsm/loaders/GLTFLoader.js', 'addons/loaders/GLTFLoader.js'],
]) {
  await build({
    entryPoints: [fileURLToPath(new URL(input, source))],
    outfile: fileURLToPath(new URL(output, target)),
    bundle: true, format: 'esm', minify: true, external: ['three'],
    target: 'es2022', legalComments: 'inline',
  });
}
await copyFile(new URL('LICENSE', source), new URL('LICENSE', target));
await writeFile(new URL('version.json', target), JSON.stringify({ package: 'three', version: metadata.version }, null, 2) + '\n');
console.log(`Vendored Three.js ${metadata.version} and GLTFLoader with its bundled helper dependencies.`);
