// Inlines src/ + data/build/data.js into one page fragment (dist/jade.html)
// for publishing as a claude.ai artifact, which supplies its own <html>/<head>/<body>.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (f) => readFileSync(join(root, f), 'utf8');

const html = read('src/index.html');
const title = html.match(/<title>.*<\/title>/)[0];
const fonts = html.match(/<link [^>]*fonts\.g[^>]*>/g).join('\n');
const body = html.match(/<body>([\s\S]*?)<script/)[1].trim();
// Keep inline scripts from closing early if data ever contains "</script".
const safe = (js) => js.replace(/<\/script/gi, '<\\/script');

const out = `${title}
${fonts}
<style>
${read('src/style.css')}
</style>
${body}
<script>${safe(read('data/build/data.js'))}</script>
<script>
${safe(read('src/app.js'))}
</script>
`;

mkdirSync(join(root, 'dist'), { recursive: true });
writeFileSync(join(root, 'dist/jade.html'), out);
console.log(`dist/jade.html (${(out.length / 1024).toFixed(1)} KB)`);
