// Headless export: renders project/project.json through a real parallax-scene-editor
// checkout in Chromium and writes out/project.gif + out/project.webm.
//
// The editor has no server-side API — GIF and PNG export run on a canvas, WebM
// through MediaRecorder — so this drives an actual browser instead of
// reimplementing the renderer. `EDITOR_DIR` must point at a parallax-scene-editor
// checkout (the GitHub Action checks one out as a sibling directory).

import { chromium } from 'playwright';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '..');
const editorDir = path.resolve(process.env.EDITOR_DIR || path.join(repoRoot, '..', 'parallax-scene-editor'));
const projectDir = path.join(repoRoot, 'project');
const outDir = path.join(repoRoot, 'out');
const step = Number(process.env.EXPORT_STEP || 1);
const port = Number(process.env.EXPORT_PORT || 8321);
const bridgeName = '.render-bridge';
const bridgeDir = path.join(editorDir, bridgeName);

const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml',
};

function copyRecursive(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dst, entry.name);
    if (entry.isDirectory()) copyRecursive(s, d);
    else fs.copyFileSync(s, d);
  }
}

function listFiles(dir, prefix = '') {
  let out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) out = out.concat(listFiles(path.join(dir, entry.name), rel));
    else if (/\.(png|jpe?g|json)$/i.test(entry.name)) out.push(rel);
  }
  return out;
}

function buildBridge() {
  fs.rmSync(bridgeDir, { recursive: true, force: true });
  copyRecursive(projectDir, bridgeDir);
  fs.renameSync(path.join(bridgeDir, 'project.json'), path.join(bridgeDir, 'scene.json'));
  const files = ['scene.json', ...listFiles(bridgeDir).filter(f => f !== 'scene.json')];
  fs.writeFileSync(path.join(bridgeDir, 'project.json'), JSON.stringify({
    name: 'pokemon-emerald-intro',
    scene: 'scene.json',
    files,
  }, null, 2));
}

function serveStatic(root) {
  return http.createServer((req, res) => {
    const url = decodeURIComponent(req.url.split('?')[0]);
    const rel = url === '/' ? '/index.html' : url;
    const filePath = path.join(root, rel);
    if (!filePath.startsWith(root)) { res.writeHead(403); res.end(); return; }
    fs.readFile(filePath, (err, data) => {
      if (err) { res.writeHead(404); res.end('not found'); return; }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(filePath)] || 'application/octet-stream' });
      res.end(data);
    });
  });
}

async function blobToBase64(page, exportFn, step) {
  return page.evaluate(async ({ exportFn, step }) => {
    const mod = await import('/src/export/index.js');
    const a = window.editor;
    const res = await mod[exportFn](a.store.scene, a.resolve, { step });
    const bytes = new Uint8Array(await res.blob.arrayBuffer());
    let binary = '';
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(binary);
  }, { exportFn, step });
}

async function main() {
  if (!fs.existsSync(path.join(editorDir, 'index.html'))) {
    throw new Error(`no parallax-scene-editor checkout at ${editorDir} (set EDITOR_DIR)`);
  }

  buildBridge();
  const server = serveStatic(editorDir);
  await new Promise(resolve => server.listen(port, resolve));

  const browser = await chromium.launch();
  const page = await browser.newPage();
  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(String(e)));

  try {
    await page.goto(`http://127.0.0.1:${port}/`);
    await page.waitForFunction(() => window.editor && window.editor.store.scene.layers.length > 0);

    const info = await page.evaluate(async bridgeName => {
      const a = window.editor;
      await a.assets.loadManifest(bridgeName);
      const scene = JSON.parse(await a.assets.readText('scene.json'));
      a.store.replace(scene, { history: false });
      a.store.dirty = false;
      a.setFrame(0);
      return { missing: a.missingCount(), layers: a.store.scene.layers.length };
    }, bridgeName);
    if (info.layers === 0) throw new Error('scene loaded with no layers');
    if (info.missing > 0) throw new Error(`${info.missing} asset(s) failed to resolve`);

    fs.mkdirSync(outDir, { recursive: true });
    const gif = await blobToBase64(page, 'exportGIF', step);
    fs.writeFileSync(path.join(outDir, 'project.gif'), Buffer.from(gif, 'base64'));
    console.log('wrote out/project.gif');

    const webm = await blobToBase64(page, 'exportWebM', step);
    fs.writeFileSync(path.join(outDir, 'project.webm'), Buffer.from(webm, 'base64'));
    console.log('wrote out/project.webm');

    if (pageErrors.length) throw new Error(`page errors during export:\n${pageErrors.join('\n')}`);
  } finally {
    await browser.close();
    server.close();
    fs.rmSync(bridgeDir, { recursive: true, force: true });
  }
}

main().catch(err => { console.error(err); process.exitCode = 1; });
