import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const [htmlPath, outputPath] = process.argv.slice(2);
if (!htmlPath || !outputPath) {
  process.stderr.write('Usage: node render_pdf.mjs <htmlPath> <outputPath>\n');
  process.exit(2);
}

const html = await readFile(htmlPath, 'utf8');
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.route('**/*', route => route.abort());
  await page.setContent(html, { waitUntil: 'load', timeout: 20_000 });
  await page.evaluate(async () => {
    await document.fonts.ready;
    window.__REPORT_READY__ = true;
  });
  await page.waitForFunction(() => window.__REPORT_READY__ === true, { timeout: 5_000 });
  await page.emulateMedia({ media: 'print' });
  await page.pdf({
    path: outputPath,
    format: 'A4',
    printBackground: true,
    preferCSSPageSize: true,
    tagged: true,
    outline: true,
    margin: { top: '0', right: '0', bottom: '0', left: '0' },
  });
  await context.close();
} finally {
  await browser.close();
}
