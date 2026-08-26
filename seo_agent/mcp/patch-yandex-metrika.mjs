import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';

const METRIKA_ENTRYPOINT = new URL(
  './node_modules/yandex-metrika-mcp/src/index.mjs',
  import.meta.url,
);

export function normalizeTotals(value) {
  if (!Array.isArray(value)) return [];
  return Array.isArray(value[0]) ? value[0] : value;
}

export function patchSource(source) {
  const replacements = [
    ['const metrics = data.totals?.[0] || [];', 'const metrics = normalizeTotals(data.totals);'],
    ['const totals = data.totals?.[0] || [];', 'const totals = normalizeTotals(data.totals);'],
  ];
  let patched = source;
  for (const [before, after] of replacements) {
    const occurrences = patched.split(before).length - 1;
    if (occurrences !== 1) {
      throw new Error(`Unexpected yandex-metrika-mcp source for: ${before}`);
    }
    patched = patched.replace(before, after);
  }
  const marker = "  function getToken() {";
  if (patched.split(marker).length - 1 !== 1) {
    throw new Error('Unexpected yandex-metrika-mcp getToken marker');
  }
  return patched.replace(
    marker,
    "  function normalizeTotals(value) {\n" +
      "    if (!Array.isArray(value)) return [];\n" +
      "    return Array.isArray(value[0]) ? value[0] : value;\n" +
      "  }\n\n" + marker,
  );
}

export async function main() {
  const path = fileURLToPath(METRIKA_ENTRYPOINT);
  const source = await readFile(path, 'utf8');
  await writeFile(path, patchSource(source), 'utf8');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
