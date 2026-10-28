// Builds the static site GitHub Pages (or any static host) serves: docs/{index.html,app.js,style.css,credits.html,favicon.svg,pool/}.
// Run the pool build first (python scripts/pool/build_pool.py). The site has no build step of its own:
// a host only has to serve this folder.
import { cpSync, rmSync, mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'docs');
const pool = join(root, 'data/build/pool');
if (!existsSync(join(pool, 'index.json'))) throw new Error('No pool found: run python scripts/pool/build_pool.py first');

for (const f of ['index.html', 'app.js', 'style.css', 'credits.html', 'favicon.svg']) rmSync(join(out, f), { force: true });
rmSync(join(out, 'pool'), { recursive: true, force: true });
mkdirSync(out, { recursive: true });

for (const f of ['app.js', 'style.css', 'credits.html', 'favicon.svg']) cpSync(join(root, 'src', f), join(out, f));
const html = readFileSync(join(root, 'src/index.html'), 'utf8')
  .replace('<script src="app.js"></script>', "<script>window.POOL_BASE = 'pool/';</script>\n  <script src=\"app.js\"></script>");
writeFileSync(join(out, 'index.html'), html);
cpSync(pool, join(out, 'pool'), { recursive: true });
writeFileSync(join(out, '.nojekyll'), '');  // serve files as they are

const files = readdirSync(join(out, 'pool'));
console.log(`docs/ ready: ${files.length} pool files`);
