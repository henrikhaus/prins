// Bundles main.js and three.js into one self-contained index.html.
// Usage: node build.mjs <dir containing node_modules with three@0.187.0, esbuild, @fontsource/archivo>
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const tools = process.argv[2];
const require = createRequire(join(tools, 'package.json'));
const esbuild = require('esbuild');

const threeVersion = JSON.parse(readFileSync(join(tools, 'node_modules/three/package.json'))).version;
if (threeVersion !== '0.187.0') throw new Error(`expected three 0.187.0, found ${threeVersion}`);

const result = await esbuild.build({
  entryPoints: [join(here, 'main.js')],
  bundle: true,
  format: 'iife',
  minify: true,
  target: 'es2020',
  write: false,
  legalComments: 'none',
  nodePaths: [join(tools, 'node_modules')],
  logLevel: 'warning',
});
const js = result.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');

const face = (w) => {
  const b64 = readFileSync(join(tools, `node_modules/@fontsource/archivo/files/archivo-latin-${w}-normal.woff2`)).toString('base64');
  return `@font-face{font-family:Archivo;font-weight:${w};font-style:normal;font-display:swap;src:url(data:font/woff2;base64,${b64}) format("woff2")}`;
};
const fonts = [400, 500, 700, 800].map(face).join('\n');

const html = readFileSync(join(here, 'template.html'), 'utf8')
  .replace('/*__FONTS__*/', () => fonts)
  .replace('/*__BUNDLE__*/', () => js);
writeFileSync(join(here, '..', 'index.html'), html);
console.log(`index.html ${(html.length / 1024 / 1024).toFixed(2)} MB (three ${threeVersion})`);
