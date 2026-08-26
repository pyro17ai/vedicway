#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import {
  PublicationLedger,
  browserStartCommand,
  loadCarouselManifest,
} from './publisher-core.mjs';
import {
  prepareCarousel,
  publishPreparedCarousel,
} from './playwright-flow.mjs';

function valueAfter(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith('--')) throw new Error(`${flag} requires a value`);
  return value;
}

export function parseRunnerArgs(argv) {
  const parsed = {
    manifestPath: null,
    cdp: null,
    profile: null,
    session: 'vedicway-tiktok',
    publish: false,
    resumeCurrent: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === '--manifest') parsed.manifestPath = valueAfter(argv, index++, flag);
    else if (flag === '--cdp') parsed.cdp = valueAfter(argv, index++, flag);
    else if (flag === '--profile') parsed.profile = valueAfter(argv, index++, flag);
    else if (flag === '--session') parsed.session = valueAfter(argv, index++, flag);
    else if (flag === '--publish') parsed.publish = true;
    else if (flag === '--resume-current') parsed.resumeCurrent = true;
    else throw new Error(`Unknown argument: ${flag}`);
  }
  if (!parsed.manifestPath) throw new Error('--manifest is required');
  if (Boolean(parsed.cdp) === Boolean(parsed.profile)) throw new Error('Choose either --cdp or --profile');
  return parsed;
}

export function cliInvocation({
  platform = process.platform,
  appData = process.env.APPDATA,
  nodePath = process.execPath,
  exists = existsSync,
} = {}) {
  if (platform !== 'win32') return { command: 'playwright-cli', prefix: [] };
  const script = appData
    ? path.win32.join(appData, 'npm', 'node_modules', '@playwright', 'cli', 'playwright-cli.js')
    : '';
  if (!script || !exists(script)) throw new Error('Global playwright-cli entrypoint was not found');
  return { command: nodePath, prefix: [script] };
}

function runCli(args, environment = process.env) {
  const invocation = cliInvocation();
  const result = spawnSync(invocation.command, [...invocation.prefix, ...args], {
    cwd: process.cwd(),
    encoding: 'utf8',
    env: environment,
    shell: false,
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error((result.stderr || result.stdout || 'playwright-cli failed').trim());
  return result.stdout.trim();
}

export function sessionStartArgs(options) {
  if (options.resumeCurrent) return null;
  return browserStartCommand(options);
}

function ensureSession(options) {
  const args = sessionStartArgs(options);
  if (args) runCli(args);
}

export function buildRunCode(fn, payload) {
  return `async page => (${fn.toString()})(page, ${JSON.stringify(payload)})`;
}

export function parseCliJson(output) {
  if (output.startsWith('### Error')) throw new Error(output.slice('### Error'.length).trim());
  try {
    return JSON.parse(output);
  } catch (error) {
    throw new Error(`playwright-cli returned non-JSON output: ${output || error.message}`);
  }
}

async function runFunction(session, fn, payload) {
  const temporary = await mkdtemp(path.join(os.tmpdir(), 'vedicway-playwright-cli-'));
  const source = path.join(temporary, 'flow.js');
  const code = `${buildRunCode(fn, payload)}\n`;
  await writeFile(source, code, 'utf8');
  try {
    const output = runCli(['--raw', `-s=${session}`, 'run-code', `--filename=${source}`]);
    return parseCliJson(output);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

async function main() {
  const options = parseRunnerArgs(process.argv.slice(2));
  const dataRoot = path.resolve('runtime/tiktok');
  const manifestPath = path.resolve(options.manifestPath);
  const { manifest, contentSha256 } = await loadCarouselManifest({ dataRoot, manifestPath });
  const runDir = path.dirname(manifest.manifest_path);
  const ledger = new PublicationLedger({ dataRoot });
  const ledgerPrepared = await ledger.prepare({
    contentSha256,
    runId: manifest.run_id,
    manifestPath: manifest.manifest_path,
  });
  if (ledgerPrepared.status === 'already_published') {
    process.stdout.write(`${JSON.stringify(ledgerPrepared)}\n`);
    return;
  }

  await mkdir(runDir, { recursive: true });
  ensureSession(options);

  const prepared = await runFunction(options.session, prepareCarousel, {
    account: manifest.account,
    title: manifest.title,
    description: manifest.description,
    slides: manifest.slides.map((slide) => slide.path),
    evidencePath: path.join(runDir, 'tiktok-prepared.png'),
    resumeCurrent: options.resumeCurrent,
  });
  if (!options.publish) {
    process.stdout.write(`${JSON.stringify({ ...prepared, ...ledgerPrepared, content_sha256: contentSha256 })}\n`);
    return;
  }

  const reservation = await ledger.reservePost({ contentSha256 });
  if (reservation.status === 'already_published') {
    process.stdout.write(`${JSON.stringify(reservation)}\n`);
    return;
  }
  try {
    const published = await runFunction(options.session, publishPreparedCarousel, {
      account: manifest.account,
      description: manifest.description,
      evidencePath: path.join(runDir, 'tiktok-published.png'),
    });
    const completed = await ledger.complete({
      contentSha256,
      outcome: 'published',
      postUrl: published.post_url,
    });
    process.stdout.write(`${JSON.stringify({ ...published, ...completed })}\n`);
  } catch (error) {
    await ledger.complete({
      contentSha256,
      outcome: 'needs_review',
      error: error.message,
    });
    throw error;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
