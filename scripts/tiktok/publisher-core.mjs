import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import {
  mkdir,
  readFile,
  realpath,
  rename,
  rmdir,
  stat,
  writeFile,
} from 'node:fs/promises';
import path from 'node:path';

const ACCOUNT = '@vedicway7';
const PROFILE_URL = `https://www.tiktok.com/${ACCOUNT}`;
const MAX_IMAGE_BYTES = 50 * 1024 * 1024;

function fail(message) {
  throw new Error(message);
}

function inside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

async function existingInside(root, candidate, label) {
  const realRoot = await realpath(path.resolve(root));
  const resolved = await realpath(path.resolve(candidate));
  if (!inside(realRoot, resolved)) fail(`${label} must stay inside the TikTok data directory`);
  return resolved;
}

async function writableInside(root, candidate, label) {
  const declaredRoot = path.resolve(root);
  const realRoot = await realpath(declaredRoot);
  const requested = path.resolve(candidate);
  if (!inside(declaredRoot, requested)) fail(`${label} must stay inside the TikTok data directory`);

  const parts = path.relative(declaredRoot, requested).split(path.sep);
  const filename = parts.pop();
  let directory = realRoot;
  for (const part of parts) {
    const next = path.join(directory, part);
    try {
      directory = await realpath(next);
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      await mkdir(next);
      directory = next;
    }
    if (!inside(realRoot, directory)) fail(`${label} must stay inside the TikTok data directory`);
  }
  return path.join(directory, filename);
}

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function validWebp(buffer) {
  return buffer.length >= 12
    && buffer.toString('ascii', 0, 4) === 'RIFF'
    && buffer.toString('ascii', 8, 12) === 'WEBP';
}

function webpSize(buffer) {
  if (!validWebp(buffer)) fail('Final slide is not a valid WebP image');
  let offset = 12;
  while (offset + 8 <= buffer.length) {
    const kind = buffer.toString('ascii', offset, offset + 4);
    const chunkSize = buffer.readUInt32LE(offset + 4);
    const data = offset + 8;
    if (data + chunkSize > buffer.length) break;
    if (kind === 'VP8X' && chunkSize >= 10) {
      return { width: 1 + buffer.readUIntLE(data + 4, 3), height: 1 + buffer.readUIntLE(data + 7, 3) };
    }
    if (kind === 'VP8 ' && chunkSize >= 10 && buffer.subarray(data + 3, data + 6).equals(Buffer.from([0x9d, 0x01, 0x2a]))) {
      return { width: buffer.readUInt16LE(data + 6) & 0x3fff, height: buffer.readUInt16LE(data + 8) & 0x3fff };
    }
    if (kind === 'VP8L' && chunkSize >= 5 && buffer[data] === 0x2f) {
      const bits = buffer.readUInt32LE(data + 1);
      return { width: (bits & 0x3fff) + 1, height: ((bits >>> 14) & 0x3fff) + 1 };
    }
    offset = data + chunkSize + (chunkSize % 2);
  }
  fail('Could not read final WebP dimensions');
}

function runFfmpeg(args, command = process.env.FFMPEG_PATH || 'ffmpeg') {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { windowsHide: true });
    let stderr = '';
    child.stderr.on('data', (chunk) => { stderr += chunk.toString('utf8'); });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(stderr.trim() || `ffmpeg exited with ${code}`));
    });
  });
}

export async function finalizeSlide({ dataRoot, sourcePath, outputPath }) {
  const realRoot = await realpath(path.resolve(dataRoot));
  const source = await existingInside(realRoot, sourcePath, 'source_path');
  const output = await writableInside(dataRoot, outputPath, 'output_path');
  if (path.extname(output).toLowerCase() !== '.webp') fail('output_path must end with .webp');
  await runFfmpeg([
    '-hide_banner', '-loglevel', 'error', '-y', '-i', source,
    '-vf', 'scale=1080:1440:force_original_aspect_ratio=decrease,pad=1080:1440:(ow-iw)/2:(oh-ih)/2:color=0xfbf6ee',
    '-frames:v', '1', '-c:v', 'libwebp', '-quality', '92', '-compression_level', '6',
    '-map_metadata', '-1', output,
  ]);
  const buffer = await readFile(output);
  const dimensions = webpSize(buffer);
  if (dimensions.width !== 1080 || dimensions.height !== 1440) fail('Final slide must be exactly 1080x1440');
  return {
    path: output,
    sha256: sha256(buffer),
    width: dimensions.width,
    height: dimensions.height,
    mime_type: 'image/webp',
    bytes: buffer.length,
  };
}

function validText(value, label, min, max) {
  if (typeof value !== 'string' || value.trim().length < min || value.trim().length > max) {
    fail(`${label} must contain ${min} to ${max} characters`);
  }
  return value.trim();
}

export async function loadCarouselManifest({ dataRoot, manifestPath }) {
  const manifestFile = await existingInside(dataRoot, manifestPath, 'manifest_path');
  let raw;
  try {
    raw = JSON.parse(await readFile(manifestFile, 'utf8'));
  } catch (error) {
    fail(`Could not parse manifest JSON: ${error.message}`);
  }
  if (raw?.version !== 1) fail('manifest version must be 1');
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$/.test(raw.run_id ?? '')) fail('run_id is invalid');
  if (raw.account !== ACCOUNT) fail(`account must be ${ACCOUNT}`);
  const topic = validText(raw.topic, 'topic', 8, 160);
  const title = validText(raw.title, 'title', 8, 90);
  const description = validText(raw.description, 'description', 1, 4000);
  if (!Array.isArray(raw.sources) || new Set(raw.sources).size < 2 || raw.sources.some((source) => {
    try { return new URL(source).protocol !== 'https:'; } catch { return true; }
  })) fail('sources must contain at least two unique HTTPS URLs');
  if (raw.image_generation?.skill !== 'imagegen' || raw.image_generation?.tool !== 'image_gen') {
    fail('image_generation must record imagegen and image_gen');
  }
  if (!Array.isArray(raw.slides) || raw.slides.length !== 6) fail('manifest must contain exactly six slides');

  const filePaths = new Set();
  const hashes = new Set();
  const slides = [];
  for (let index = 0; index < 6; index += 1) {
    const slide = raw.slides[index];
    if (slide?.position !== index + 1) fail('slides must be ordered from position 1 through 6');
    const requested = path.isAbsolute(slide.path)
      ? slide.path
      : path.resolve(path.dirname(manifestFile), slide.path);
    const file = await existingInside(dataRoot, requested, `slides[${index}].path`);
    const buffer = await readFile(file);
    const info = await stat(file);
    const actualHash = sha256(buffer);
    if (path.extname(file).toLowerCase() !== '.webp' || slide.mime_type !== 'image/webp' || !validWebp(buffer)) {
      fail('Every slide must be a valid WebP file');
    }
    if (info.size <= 0 || info.size > MAX_IMAGE_BYTES) fail('Every slide must be between 1 byte and 50 MB');
    if (slide.sha256 !== actualHash) fail(`Slide ${index + 1} SHA-256 does not match its file`);
    const dimensions = webpSize(buffer);
    if (dimensions.width !== 1080 || dimensions.height !== 1440) {
      fail('Every slide actual dimensions must be 1080x1440');
    }
    if (slide.width !== 1080 || slide.height !== 1440) fail('Every slide must be declared as 1080x1440');
    filePaths.add(file.toLowerCase());
    hashes.add(actualHash);
    slides.push({ ...slide, path: file, sha256: actualHash });
  }
  if (filePaths.size !== 6 || hashes.size !== 6) fail('Carousel must contain six unique image files');

  const manifest = {
    ...raw,
    topic,
    title,
    description,
    slides,
    manifest_path: manifestFile,
  };
  const contentSha256 = sha256(Buffer.from(stableJson({ ...manifest, manifest_path: undefined }), 'utf8'));
  return { manifest, contentSha256 };
}

export function browserStartCommand({ session, cdp, profile }) {
  if (!session) fail('session is required');
  if (cdp && profile) fail('Choose either cdp or profile');
  if (cdp) return [`-s=${session}`, 'attach', `--cdp=${cdp}`];
  if (profile) return [`-s=${session}`, 'open', PROFILE_URL, `--profile=${profile}`];
  fail('cdp or profile is required');
}

export class PublicationLedger {
  constructor({ dataRoot }) {
    this.dataRoot = path.resolve(dataRoot);
    this.file = path.join(this.dataRoot, 'state.json');
    this.lock = path.join(this.dataRoot, 'state.lock');
  }

  async read() {
    try {
      const state = JSON.parse(await readFile(this.file, 'utf8'));
      return state?.version === 1 && state.publications
        ? state
        : { version: 1, publications: {} };
    } catch (error) {
      if (error.code === 'ENOENT') return { version: 1, publications: {} };
      throw error;
    }
  }

  async write(state) {
    await mkdir(this.dataRoot, { recursive: true });
    const temporary = `${this.file}.${process.pid}.tmp`;
    await writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, 'utf8');
    await rename(temporary, this.file);
  }

  async locked(operation) {
    await mkdir(this.dataRoot, { recursive: true });
    try {
      await mkdir(this.lock);
    } catch (error) {
      if (error.code === 'EEXIST') fail('Another publication process owns the Post reservation');
      throw error;
    }
    try {
      return await operation();
    } finally {
      await rmdir(this.lock).catch(() => {});
    }
  }

  async prepare({ contentSha256, runId, manifestPath }) {
    return this.locked(async () => {
      const state = await this.read();
      const current = state.publications[contentSha256];
      if (current?.status === 'published') return { ...current, status: 'already_published', content_sha256: contentSha256 };
      if (current?.status === 'needs_review') fail('This carousel needs review before retry');
      if (current?.status === 'publishing') fail('This carousel already owns a Post attempt');
      const record = {
        status: 'prepared',
        run_id: runId,
        manifest_path: path.resolve(manifestPath),
        updated_at: new Date().toISOString(),
      };
      state.publications[contentSha256] = record;
      await this.write(state);
      return { ...record, content_sha256: contentSha256 };
    });
  }

  async reservePost({ contentSha256 }) {
    return this.locked(async () => {
      const state = await this.read();
      const current = state.publications[contentSha256];
      if (current?.status === 'published') return { ...current, status: 'already_published', content_sha256: contentSha256 };
      if (current?.status === 'needs_review') fail('This carousel needs review before retry');
      if (current?.status !== 'prepared') fail('Carousel is not prepared or another process owns the Post attempt');
      const record = { ...current, status: 'publishing', updated_at: new Date().toISOString() };
      state.publications[contentSha256] = record;
      await this.write(state);
      return { ...record, content_sha256: contentSha256 };
    });
  }

  async complete({ contentSha256, outcome, postUrl, error }) {
    return this.locked(async () => {
      const state = await this.read();
      const current = state.publications[contentSha256];
      if (current?.status === 'published' && outcome === 'published' && current.post_url === postUrl) {
        return { ...current, status: 'already_published', content_sha256: contentSha256 };
      }
      if (current?.status !== 'publishing') fail('No reserved Post attempt exists for this carousel');
      if (outcome === 'published') {
        if (!/^https:\/\/www\.tiktok\.com\/@vedicway7\/(?:photo|video)\/\d+/.test(postUrl ?? '')) {
          fail('A verified @vedicway7 post URL is required');
        }
        state.publications[contentSha256] = {
          ...current,
          status: 'published',
          post_url: postUrl,
          updated_at: new Date().toISOString(),
        };
      } else if (outcome === 'needs_review') {
        state.publications[contentSha256] = {
          ...current,
          status: 'needs_review',
          error: error || 'TikTok submission was not confirmed',
          updated_at: new Date().toISOString(),
        };
      } else {
        fail('outcome must be published or needs_review');
      }
      await this.write(state);
      return { ...state.publications[contentSha256], content_sha256: contentSha256 };
    });
  }

  async reconcilePublished({ contentSha256, postUrl }) {
    return this.locked(async () => {
      if (!/^https:\/\/www\.tiktok\.com\/@vedicway7\/(?:photo|video)\/\d+/.test(postUrl ?? '')) {
        fail('A verified @vedicway7 post URL is required');
      }
      const state = await this.read();
      const current = state.publications[contentSha256];
      if (current?.status === 'published' && current.post_url === postUrl) {
        return { ...current, status: 'already_published', content_sha256: contentSha256 };
      }
      if (current?.status !== 'needs_review') {
        fail('Only a needs_review publication can be reconciled');
      }
      const { error: _error, ...withoutError } = current;
      state.publications[contentSha256] = {
        ...withoutError,
        status: 'published',
        post_url: postUrl,
        updated_at: new Date().toISOString(),
      };
      await this.write(state);
      return { ...state.publications[contentSha256], content_sha256: contentSha256 };
    });
  }
}
