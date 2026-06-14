import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const jsPath = path.join(__dirname, '..', 'captured', 'assets', 'index.41f20bb5.js');
const text = fs.readFileSync(jsPath, 'utf8');

const routes = new Set();

for (const m of text.matchAll(/path:"([^"]+)"/g)) routes.add(m[1]);
for (const m of text.matchAll(/"\/[a-zA-Z0-9_/-]{2,60}"/g)) {
  const s = m[0].slice(1, -1);
  if (!s.includes('.') && !s.includes('http')) routes.add(s);
}

const chunks = [...new Set(text.match(/"[a-zA-Z][a-zA-Z0-9_-]{2,40}":/g)?.map((x) => x.slice(1, -2)) ?? [])]
  .filter((n) => /^(admin|dashboard|students|groups|finance|reports|leads|teachers)/.test(n) || n.includes('Report'));

const out = {
  extractedAt: new Date().toISOString(),
  routeCount: routes.size,
  routes: [...routes].sort(),
  lazyChunks: chunks.sort(),
};

fs.writeFileSync(path.join(__dirname, '..', 'captured', 'frontend-routes.json'), JSON.stringify(out, null, 2));
console.log('routes:', out.routeCount, 'chunks:', chunks.length);
