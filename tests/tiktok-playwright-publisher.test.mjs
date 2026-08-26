import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

import {
  PublicationLedger,
  browserStartCommand,
  finalizeSlide,
  loadCarouselManifest,
} from '../scripts/tiktok/publisher-core.mjs';

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { windowsHide: true });
    let stderr = '';
    child.stderr.on('data', (chunk) => { stderr += chunk.toString('utf8'); });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(stderr || `${command} exited with ${code}`));
    });
  });
}
import {
  prepareCarousel,
  publishPreparedCarousel,
} from '../scripts/tiktok/playwright-flow.mjs';
import {
  buildRunCode,
  cliInvocation,
  parseCliJson,
  parseRunnerArgs,
} from '../scripts/tiktok/playwright-runner.mjs';

async function manifestFixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'vedicway-tiktok-playwright-'));
  const runDir = path.join(root, 'runs', '20260823-ascendant');
  const slidesDir = path.join(runDir, 'slides');
  await mkdir(slidesDir, { recursive: true });
  const slides = [];
  for (let position = 1; position <= 6; position += 1) {
    const file = path.join(slidesDir, `${String(position).padStart(2, '0')}.webp`);
    const dimensions = Buffer.alloc(10);
    dimensions.writeUIntLE(1080 - 1, 4, 3);
    dimensions.writeUIntLE(1440 - 1, 7, 3);
    const body = Buffer.concat([
      Buffer.from('VP8X'), Buffer.from([10, 0, 0, 0]), dimensions,
      Buffer.from('EXIF'), Buffer.from([1, 0, 0, 0]), Buffer.from([position, 0]),
    ]);
    const riffSize = Buffer.alloc(4);
    riffSize.writeUInt32LE(4 + body.length);
    const buffer = Buffer.concat([Buffer.from('RIFF'), riffSize, Buffer.from('WEBP'), body]);
    await writeFile(file, buffer);
    slides.push({
      position,
      path: `slides/${String(position).padStart(2, '0')}.webp`,
      sha256: createHash('sha256').update(buffer).digest('hex'),
      width: 1080,
      height: 1440,
      mime_type: 'image/webp',
    });
  }
  const manifest = {
    version: 1,
    run_id: '20260823-ascendant',
    account: '@vedicway7',
    topic: 'Что такое асцендент и зачем нужны точное время и место рождения',
    title: 'Асцендент: зачем нужны время и город рождения',
    description: 'Разбираем восходящий знак и первый дом натальной карты. #асцендент #астрология #натальнаякарта',
    sources: [
      'https://www.astro.com/astrowiki/en/Ascendant',
      'https://www.oxfordlearnersdictionaries.com/definition/english/rising-sign',
    ],
    image_generation: { skill: 'imagegen', tool: 'image_gen' },
    slides,
  };
  const manifestPath = path.join(runDir, 'manifest.json');
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  return { manifest, manifestPath, root };
}

test('loadCarouselManifest resolves six verified WebP files and returns a stable content hash', async () => {
  const { manifestPath, root } = await manifestFixture();

  const first = await loadCarouselManifest({ dataRoot: root, manifestPath });
  const second = await loadCarouselManifest({ dataRoot: root, manifestPath });

  assert.equal(first.manifest.account, '@vedicway7');
  assert.equal(first.manifest.slides.length, 6);
  assert.ok(first.manifest.slides.every((slide) => path.isAbsolute(slide.path)));
  assert.match(first.contentSha256, /^[a-f0-9]{64}$/);
  assert.equal(second.contentSha256, first.contentSha256);
});

test('finalizeSlide converts an imagegen source into an exact 1080x1440 WebP', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'vedicway-tiktok-finalize-'));
  const source = path.join(root, 'raw.png');
  const output = path.join(root, 'slides', '01.webp');
  await run('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
    'color=c=#fbf6ee:s=1024x1536', '-frames:v', '1', source,
  ]);

  const result = await finalizeSlide({ dataRoot: root, sourcePath: source, outputPath: output });

  assert.equal(result.width, 1080);
  assert.equal(result.height, 1440);
  assert.equal(result.mime_type, 'image/webp');
  assert.match(result.sha256, /^[a-f0-9]{64}$/);
});

test('finalizeSlide accepts an output reached through the VPS runtime symlink', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'vedicway-tiktok-symlink-'));
  const realRoot = path.join(root, 'shared', 'runtime', 'tiktok');
  const linkedRoot = path.join(root, 'release', 'runtime', 'tiktok');
  await mkdir(path.dirname(linkedRoot), { recursive: true });
  await mkdir(path.join(realRoot, 'raw'), { recursive: true });
  await symlink(realRoot, linkedRoot, process.platform === 'win32' ? 'junction' : 'dir');
  const source = path.join(linkedRoot, 'raw', '01.png');
  const output = path.join(linkedRoot, 'slides', '01.webp');
  await run('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
    'color=c=#fbf6ee:s=1024x1536', '-frames:v', '1', source,
  ]);

  const result = await finalizeSlide({ dataRoot: linkedRoot, sourcePath: source, outputPath: output });

  assert.equal(result.path, path.join(realRoot, 'slides', '01.webp'));
  assert.equal(result.width, 1080);
  assert.equal(result.height, 1440);
});

test('loadCarouselManifest rejects a changed slide instead of publishing unreviewed bytes', async () => {
  const { manifestPath, root } = await manifestFixture();
  await writeFile(
    path.join(path.dirname(manifestPath), 'slides', '03.webp'),
    Buffer.concat([
      Buffer.from('RIFF'),
      Buffer.from([0, 0, 0, 0]),
      Buffer.from('WEBP'),
      Buffer.from('changed-but-still-webp'),
    ]),
  );

  await assert.rejects(
    loadCarouselManifest({ dataRoot: root, manifestPath }),
    /SHA-256 does not match/i,
  );
});

test('loadCarouselManifest reads actual WebP dimensions instead of trusting manifest metadata', async () => {
  const { manifest, manifestPath, root } = await manifestFixture();
  const slidePath = path.join(path.dirname(manifestPath), 'slides', '01.webp');
  await run('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
    'color=c=#fbf6ee:s=100x100', '-frames:v', '1', slidePath,
  ]);
  const buffer = await readFile(slidePath);
  manifest.slides[0].sha256 = createHash('sha256').update(buffer).digest('hex');
  await writeFile(manifestPath, JSON.stringify(manifest), 'utf8');

  await assert.rejects(
    loadCarouselManifest({ dataRoot: root, manifestPath }),
    /actual dimensions must be 1080x1440/i,
  );
});

test('loadCarouselManifest rejects every TikTok account except @vedicway7', async () => {
  const { manifest, manifestPath, root } = await manifestFixture();
  manifest.account = '@someone_else';
  await writeFile(manifestPath, JSON.stringify(manifest), 'utf8');

  await assert.rejects(
    loadCarouselManifest({ dataRoot: root, manifestPath }),
    /account must be @vedicway7/i,
  );
});

test('browserStartCommand attaches to the already running Chrome through CDP', () => {
  assert.deepEqual(
    browserStartCommand({ session: 'vedicway-tiktok', cdp: 'chrome' }),
    ['-s=vedicway-tiktok', 'attach', '--cdp=chrome'],
  );
});

test('browserStartCommand opens the VPS persistent profile in headless mode', () => {
  assert.deepEqual(
    browserStartCommand({
      session: 'vedicway-tiktok',
      profile: '/srv/vedicway/tiktok-profile',
    }),
    [
      '-s=vedicway-tiktok',
      'open',
      'https://www.tiktok.com/@vedicway7',
      '--profile=/srv/vedicway/tiktok-profile',
    ],
  );
});

test('PublicationLedger lets only one concurrent process reserve the Post click', async () => {
  const { manifestPath, root } = await manifestFixture();
  const { contentSha256 } = await loadCarouselManifest({ dataRoot: root, manifestPath });
  const first = new PublicationLedger({ dataRoot: root });
  const second = new PublicationLedger({ dataRoot: root });
  await first.prepare({ contentSha256, runId: '20260823-ascendant', manifestPath });

  const settled = await Promise.allSettled([
    first.reservePost({ contentSha256 }),
    second.reservePost({ contentSha256 }),
  ]);

  assert.equal(settled.filter((item) => item.status === 'fulfilled').length, 1);
  assert.equal(settled.filter((item) => item.status === 'rejected').length, 1);
});

test('PublicationLedger keeps an uncertain submission in needs_review and blocks retry', async () => {
  const { manifestPath, root } = await manifestFixture();
  const { contentSha256 } = await loadCarouselManifest({ dataRoot: root, manifestPath });
  const ledger = new PublicationLedger({ dataRoot: root });
  await ledger.prepare({ contentSha256, runId: '20260823-ascendant', manifestPath });
  await ledger.reservePost({ contentSha256 });
  await ledger.complete({
    contentSha256,
    outcome: 'needs_review',
    error: 'TikTok did not confirm the Post action',
  });

  await assert.rejects(
    ledger.reservePost({ contentSha256 }),
    /needs review/i,
  );
});

test('PublicationLedger reconciles a needs_review attempt after TikTok Studio verifies its URL', async () => {
  const { manifestPath, root } = await manifestFixture();
  const { contentSha256 } = await loadCarouselManifest({ dataRoot: root, manifestPath });
  const ledger = new PublicationLedger({ dataRoot: root });
  await ledger.prepare({ contentSha256, runId: '20260823-ascendant', manifestPath });
  await ledger.reservePost({ contentSha256 });
  await ledger.complete({ contentSha256, outcome: 'needs_review', error: 'profile feed returned 403' });

  const reconciled = await ledger.reconcilePublished({
    contentSha256,
    postUrl: 'https://www.tiktok.com/@vedicway7/photo/999',
  });

  assert.equal(reconciled.status, 'published');
  assert.equal(reconciled.post_url, 'https://www.tiktok.com/@vedicway7/photo/999');
  assert.equal('error' in reconciled, false);
});

test('PublicationLedger accepts only a verified @vedicway7 publication URL', async () => {
  const { manifestPath, root } = await manifestFixture();
  const { contentSha256 } = await loadCarouselManifest({ dataRoot: root, manifestPath });
  const ledger = new PublicationLedger({ dataRoot: root });
  await ledger.prepare({ contentSha256, runId: '20260823-ascendant', manifestPath });
  await ledger.reservePost({ contentSha256 });

  await assert.rejects(
    ledger.complete({
      contentSha256,
      outcome: 'published',
      postUrl: 'https://www.tiktok.com/@someone_else/photo/123',
    }),
    /verified @vedicway7 post URL/i,
  );
});

test('prepareCarousel accepts TikTok current div-based Everyone control', async () => {
  const state = {
    url: 'about:blank',
    title: '',
    description: '',
    files: [],
    postClicks: 0,
    screenshot: null,
    soundQuery: '',
    soundSelected: '',
  };
  const locator = (kind) => ({
    first() { return this; },
    filter() { return this; },
    nth(index) { return locator(`sound-${index}`); },
    getByRole(role) {
      if (role === 'button' && kind.startsWith('sound-')) return locator(`use-${kind.slice(6)}`);
      return locator('other');
    },
    async count() { return 0; },
    async click() {
      if (kind === 'post') state.postClicks += 1;
      if (kind.startsWith('use-')) state.soundSelected = kind === 'use-0' ? 'Ambient One' : 'Ambient Two';
    },
    async fill(value) {
      if (kind === 'title') state.title = value;
      if (kind === 'description') state.description = value;
      if (kind === 'sound-search') state.soundQuery = value;
    },
    async press() {},
    async inputValue() { return state.title; },
    async innerText() {
      if (kind === 'description') return state.description;
      if (kind === 'visibility') return 'Who can see this post';
      if (kind === 'uploaded') return '6 photos uploaded. Drag and drop to reorder.';
      if (kind === 'sound-0') return 'Ambient One\n01:00 · Artist One\nUse';
      if (kind === 'sound-1') return 'Ambient Two\n01:00 · Artist Two\nUse';
      return '';
    },
    async allTextContents() {
      return kind === 'comboboxes' ? [state.description, ''] : [];
    },
    async isChecked() { return true; },
    async isEnabled() { return true; },
    async isVisible() {
      return kind === 'own-profile'
        || kind === 'everyone'
        || (kind === 'replace-sound' && Boolean(state.soundSelected));
    },
    async setInputFiles(files) { state.files = files; },
    async waitFor() {},
    locator() { return locator(kind); },
    async evaluateAll() { return []; },
  });
  const page = {
    async goto(url) { state.url = url; },
    url() { return state.url; },
    async waitForTimeout() {},
    async screenshot({ path: screenshotPath }) { state.screenshot = screenshotPath; },
    getByPlaceholder() { return locator('title'); },
    getByText(pattern) {
      if (String(pattern).includes('photos uploaded')) return locator('uploaded');
      if (String(pattern).includes('Who can see')) return locator('visibility');
      if (String(pattern).includes('Replace')) return locator('replace-sound');
      if (String(pattern).includes('Everyone')) return locator('everyone');
      return locator('other');
    },
    getByRole(role, options = {}) {
      if (role === 'combobox') return locator('comboboxes');
      if (role === 'button' && String(options.name).includes('Edit profile')) return locator('edit-profile');
      if (role === 'button' && String(options.name).includes('Add sound')) return locator('add-sound');
      if (role === 'button' && options.name === 'Post') return locator('post');
      if (role === 'textbox' && String(options.name).includes('Search sounds')) return locator('sound-search');
      if (role === 'listitem') {
        const results = locator('sound-results');
        results.count = async () => 2;
        return results;
      }
      return locator('other');
    },
    locator(selector) {
      if (selector === 'input[type="file"]') return locator('file');
      if (selector.includes('contenteditable')) return locator('description');
      if (selector.includes('/photo/')) return locator('posts');
      if (selector === 'a[href="/@vedicway7"]') return locator('own-profile');
      return locator('other');
    },
  };
  const slides = Array.from({ length: 6 }, (_, index) => `/tmp/${index + 1}.webp`);
  const originalRandom = Math.random;
  Math.random = () => 0.75;

  let result;
  try {
    result = await prepareCarousel(page, {
      account: '@vedicway7',
      title: 'Асцендент: зачем нужны время и город рождения',
      description: 'Описание карусели #асцендент #астрология #натальнаякарта',
      slides,
      evidencePath: '/tmp/prepared.png',
    });
  } finally {
    Math.random = originalRandom;
  }

  assert.deepEqual(state.files, slides);
  assert.equal(state.title, 'Асцендент: зачем нужны время и город рождения');
  assert.equal(state.postClicks, 0);
  assert.equal(state.soundQuery, 'ambient');
  assert.equal(state.soundSelected, 'Ambient Two');
  assert.equal(state.screenshot, '/tmp/prepared.png');
  assert.equal(result.status, 'prepared');
  assert.equal(result.sound, 'Ambient Two');
});

test('prepareCarousel resumes the current draft without uploading again and replaces stale text', async () => {
  const expectedDescription = 'Описание карусели #асцендент #астрология #натальнаякарта';
  const state = {
    title: 'Асцендент: зачем нужны время и город рождения',
    description: 'устаревшее описание',
    files: [],
    addSoundClicks: 0,
    soundUseClicks: 0,
  };
  const locator = (kind) => ({
    first() { return this; },
    filter() { return this; },
    nth() { return locator('sound-result'); },
    getByRole() { return locator('use-sound'); },
    async click() {
      if (kind === 'add-sound') state.addSoundClicks += 1;
      if (kind === 'use-sound') state.soundUseClicks += 1;
    },
    async fill(value) {
      if (kind === 'title') state.title = value;
      if (kind === 'description') {
        state.description = value === '' ? '' : state.description + value;
      }
    },
    async inputValue() { return state.title; },
    async innerText() {
      if (kind === 'description') return state.description;
      if (kind === 'sound-result') return 'New Ambient\n01:00 · Artist\nUse';
      return '';
    },
    async allTextContents() {
      return kind === 'comboboxes' ? [state.description, '', 'Everyone'] : [];
    },
    async isChecked() { return true; },
    async isEnabled() { return true; },
    async isVisible() { return kind === 'replace-sound'; },
    async setInputFiles(files) { state.files = files; },
    async waitFor() {},
    async press() {},
    async count() { return kind === 'sound-results' ? 1 : 0; },
    async evaluateAll() { return []; },
  });
  const page = {
    url() { return 'https://www.tiktok.com/tiktokstudio/upload/post/photo'; },
    async screenshot() {},
    async waitForTimeout() {},
    getByPlaceholder() { return locator('title'); },
    getByText(pattern) {
      if (String(pattern).includes('Replace')) return locator('replace-sound');
      return locator('uploaded');
    },
    getByRole(role, options = {}) {
      if (role === 'combobox') return locator('comboboxes');
      if (role === 'radio') return locator('now');
      if (role === 'button' && String(options.name).includes('Add sound')) return locator('add-sound');
      if (role === 'button' && options.name === 'Post') return locator('post');
      if (role === 'textbox') return locator('sound-search');
      if (role === 'listitem') return locator('sound-results');
      if (role === 'button') return locator('use-sound');
      return locator('other');
    },
    locator(selector) {
      if (selector.includes('contenteditable')) return locator('description');
      if (selector === 'input[type="file"]') return locator('file');
      return locator('other');
    },
  };

  const result = await prepareCarousel(page, {
    account: '@vedicway7',
    title: 'Асцендент: зачем нужны время и город рождения',
    description: expectedDescription,
    slides: Array.from({ length: 6 }, (_, index) => `/tmp/${index + 1}.webp`),
    evidencePath: '/tmp/prepared.png',
    resumeCurrent: true,
  });

  assert.equal(result.status, 'prepared');
  assert.deepEqual(state.files, []);
  assert.equal(state.description, expectedDescription);
  assert.equal(state.addSoundClicks, 0);
  assert.equal(state.soundUseClicks, 0);
});

test('publishPreparedCarousel clicks Post once and verifies the new photo through TikTok Studio', async () => {
  const description = 'Описание карусели #асцендент #астрология #натальнаякарта';
  const state = { postClicks: 0, verificationClosed: false, responseHandler: null };
  const newPostUrl = 'https://www.tiktok.com/@vedicway7/photo/999';
  const locator = (kind) => ({
    async click() { if (kind === 'post') state.postClicks += 1; },
    async count() { return kind === 'acknowledgement' && state.postClicks === 1 ? 1 : 0; },
    async isEnabled() { return true; },
  });
  const verificationPage = {
    on(event, handler) { if (event === 'response') state.responseHandler = handler; },
    async goto() {
      await state.responseHandler?.({
        url: () => 'https://www.tiktok.com/tiktok/creator/manage/item_list/v1/?aid=1988',
        ok: () => true,
        json: async () => ({
          item_list: [{
            item_id: '999',
            item_type: 2,
            create_time: String(Math.floor(Date.now() / 1000)),
            desc: description,
          }],
        }),
      });
    },
    async waitForTimeout() {},
    async screenshot() {},
    async close() { state.verificationClosed = true; },
  };
  const page = {
    url() { return 'https://www.tiktok.com/tiktokstudio/upload/post/photo'; },
    getByRole() { return locator('post'); },
    getByText() { return locator('acknowledgement'); },
    async waitForTimeout() {},
    context() { return { async newPage() { return verificationPage; } }; },
  };

  const result = await publishPreparedCarousel(page, {
    account: '@vedicway7',
    description,
    evidencePath: '/tmp/published.png',
  });

  assert.equal(state.postClicks, 1);
  assert.equal(state.verificationClosed, true);
  assert.deepEqual(result, { status: 'published', post_url: newPostUrl, evidence_path: '/tmp/published.png' });
});

test('parseRunnerArgs selects one browser source and keeps publication opt-in', () => {
  assert.deepEqual(
    parseRunnerArgs([
      '--manifest', 'runtime/tiktok/runs/a/manifest.json',
      '--cdp', 'chrome',
      '--session', 'vedicway-tiktok-local',
      '--resume-current',
    ]),
    {
      manifestPath: 'runtime/tiktok/runs/a/manifest.json',
      cdp: 'chrome',
      profile: null,
      session: 'vedicway-tiktok-local',
      publish: false,
      resumeCurrent: true,
    },
  );
});

test('parseRunnerArgs rejects simultaneous CDP and persistent profile settings', () => {
  assert.throws(
    () => parseRunnerArgs([
      '--manifest', 'manifest.json',
      '--cdp', 'chrome',
      '--profile', '/srv/profile',
    ]),
    /either --cdp or --profile/i,
  );
});

test('runner starts a browser only for a fresh preparation', async () => {
  const { sessionStartArgs } = await import('../scripts/tiktok/playwright-runner.mjs');
  const options = {
    cdp: null,
    profile: 'runtime/tiktok/chromium-profile',
    session: 'vedicway-tiktok',
  };

  assert.deepEqual(sessionStartArgs({ ...options, resumeCurrent: false }), [
    '-s=vedicway-tiktok',
    'open',
    'https://www.tiktok.com/@vedicway7',
    '--profile=runtime/tiktok/chromium-profile',
  ]);
  assert.equal(sessionStartArgs({ ...options, resumeCurrent: true }), null);
});

test('buildRunCode executes with its payload when process.env is unavailable', async () => {
  const flow = async (page, payload) => ({ page: page.name, title: payload.title });
  const source = buildRunCode(flow, { title: 'Асцендент' });
  const executable = vm.runInNewContext(`(${source})`, {});

  assert.equal(
    JSON.stringify(await executable({ name: 'studio' })),
    '{"page":"studio","title":"Асцендент"}',
  );
});

test('parseCliJson preserves the original Playwright error', () => {
  assert.throws(
    () => parseCliJson('### Error\nError: TikTok title did not persist'),
    /TikTok title did not persist/,
  );
});

test('cliInvocation runs the Windows playwright-cli entrypoint without a command shell', () => {
  assert.deepEqual(
    cliInvocation({
      platform: 'win32',
      appData: 'C:\\Users\\Huawei\\AppData\\Roaming',
      nodePath: 'C:\\Program Files\\nodejs\\node.exe',
      exists: () => true,
    }),
    {
      command: 'C:\\Program Files\\nodejs\\node.exe',
      prefix: ['C:\\Users\\Huawei\\AppData\\Roaming\\npm\\node_modules\\@playwright\\cli\\playwright-cli.js'],
    },
  );
});
