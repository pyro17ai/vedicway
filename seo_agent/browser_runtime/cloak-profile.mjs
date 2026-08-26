#!/usr/bin/env node
import fs from 'node:fs';
import process from 'node:process';
import { launchPersistentContext } from 'cloakbrowser';

const profileName = process.env.VEDICWAY_BROWSER_PROFILE_NAME;
const userDataDir = process.env.VEDICWAY_BROWSER_USER_DATA_DIR;
const cdpPort = process.env.VEDICWAY_BROWSER_CDP_PORT;
const startUrl = process.env.VEDICWAY_BROWSER_START_URL || 'about:blank';
const headless = process.env.VEDICWAY_BROWSER_HEADLESS !== '0';
const seed = process.env.VEDICWAY_BROWSER_FINGERPRINT_SEED;

if (!profileName || !userDataDir || !cdpPort) {
  throw new Error('VEDICWAY_BROWSER_PROFILE_NAME, VEDICWAY_BROWSER_USER_DATA_DIR and VEDICWAY_BROWSER_CDP_PORT are required');
}

fs.mkdirSync(userDataDir, { recursive: true });
const args = [
  '--remote-debugging-address=0.0.0.0',
  `--remote-debugging-port=${cdpPort}`,
  '--no-first-run',
  '--no-default-browser-check',
];
if (seed) args.push(`--fingerprint=${seed}`);

const context = await launchPersistentContext({
  userDataDir,
  headless,
  timezone: 'Europe/Moscow',
  locale: 'ru-RU',
  geoip: false,
  humanize: true,
  humanPreset: 'careful',
  args,
});

const page = context.pages()[0] || await context.newPage();
await page.goto(startUrl, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => null);
process.stdout.write(`${JSON.stringify({ status: 'running', profileName, cdpPort, headless })}\n`);

async function shutdown() {
  await context.close().catch(() => null);
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
await new Promise(() => {});
