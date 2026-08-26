import sharp from 'sharp';

export const VK_API_VERSION = '5.199';
const VK_API_BASE = 'https://api.vk.com/method';

export class VkApiError extends Error {
  constructor(error) {
    super(`VK API Error ${error.error_code}: ${error.error_msg}`);
    this.name = 'VkApiError';
    this.code = error.error_code;
    this.details = error;
  }
}

export function getConfig(env = process.env) {
  const groupId = Number(env.VK_GROUP_ID);
  if (!Number.isInteger(groupId) || groupId <= 0) {
    throw new Error('VK_GROUP_ID must be a positive community id without minus sign');
  }
  if (!env.VK_GROUP_ACCESS_TOKEN) {
    throw new Error('VK_GROUP_ACCESS_TOKEN environment variable is required');
  }
  if (!env.VK_USER_ACCESS_TOKEN) {
    throw new Error('VK_USER_ACCESS_TOKEN is required for photos.getWallUploadServer');
  }
  return {
    groupId,
    ownerId: -groupId,
    groupToken: env.VK_GROUP_ACCESS_TOKEN,
    userToken: env.VK_USER_ACCESS_TOKEN,
  };
}

export async function callVk(method, params = {}, token) {
  if (!token) throw new Error(`No VK access token provided for ${method}`);
  const body = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') body.set(key, String(value));
  }
  body.set('access_token', token);
  body.set('v', VK_API_VERSION);
  const response = await fetch(`${VK_API_BASE}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!response.ok) throw new Error(`VK HTTP Error ${response.status} while calling ${method}`);
  const data = await response.json();
  if (data.error) throw new VkApiError(data.error);
  return data.response;
}

export function normalizePublishDate(publishDate) {
  if (publishDate === undefined || publishDate === null || publishDate === '') return undefined;
  if (typeof publishDate === 'number') {
    if (!Number.isFinite(publishDate) || publishDate <= 0) {
      throw new Error('publish_date must be a positive Unix timestamp in seconds');
    }
    return Math.trunc(publishDate);
  }
  if (typeof publishDate === 'string') {
    const value = publishDate.trim();
    if (!value) return undefined;
    if (/^\d+$/.test(value)) return normalizePublishDate(Number(value));
    const parsed = Date.parse(value);
    if (Number.isNaN(parsed)) {
      throw new Error('publish_date must be Unix seconds or a valid ISO 8601 date string');
    }
    return Math.floor(parsed / 1000);
  }
  throw new Error('publish_date must be Unix seconds or a valid ISO 8601 date string');
}

export function validatePublicVedicWayImageUrl(image) {
  try {
    const url = new URL(image);
    if (
      url.protocol !== 'https:'
      || url.hostname !== 'vedicway.ru'
      || !url.pathname.startsWith('/media/articles/')
      || url.username
      || url.password
    ) throw new Error();
    return url.toString();
  } catch {
    throw new Error('image must be a public HTTPS VedicWay article media URL');
  }
}

export async function normalizeVkPhoto(bytes) {
  const jpeg = await sharp(bytes, { failOn: 'error', limitInputPixels: 20_000_000 })
    .rotate()
    .flatten({ background: '#ffffff' })
    .jpeg({ quality: 90, mozjpeg: true })
    .toBuffer();
  return { blob: new Blob([jpeg], { type: 'image/jpeg' }), filename: 'photo.jpg' };
}

async function imageToBlob(image) {
  const url = validatePublicVedicWayImageUrl(image);
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to download image: HTTP ${response.status}`);
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.startsWith('image/')) throw new Error('URL did not return an image');
  return normalizeVkPhoto(Buffer.from(await response.arrayBuffer()));
}

async function uploadWallPhotoWithToken({ groupId, token, image, caption }) {
  const { blob, filename } = await imageToBlob(image);
  let uploaded;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const server = await callVk('photos.getWallUploadServer', { group_id: groupId }, token);
    if (!server?.upload_url) throw new Error('photos.getWallUploadServer did not return upload_url');
    const form = new FormData();
    form.append('photo', blob, filename);
    const response = await fetch(server.upload_url, { method: 'POST', body: form });
    if (!response.ok) {
      if ((response.status === 429 || response.status >= 500) && attempt < 3) continue;
      throw new Error(`VK upload HTTP Error ${response.status}`);
    }
    uploaded = await response.json();
    const photo = typeof uploaded.photo === 'string' ? uploaded.photo.trim() : uploaded.photo;
    if (
      photo
      && photo !== '[]'
      && uploaded.server !== undefined
      && uploaded.server !== null
      && uploaded.hash
    ) break;
    uploaded = undefined;
  }
  if (!uploaded) throw new Error('VK photo upload response is incomplete after 3 attempts');
  const saved = await callVk('photos.saveWallPhoto', {
    group_id: groupId, server: uploaded.server, photo: uploaded.photo, hash: uploaded.hash, caption,
  }, token);
  const photo = Array.isArray(saved) ? saved[0] : null;
  if (!photo?.owner_id || !photo?.id) throw new Error('photos.saveWallPhoto did not return a photo');
  return { ...photo, attachment: `photo${photo.owner_id}_${photo.id}` };
}

export async function uploadWallPhoto(config, { image, caption }) {
  return uploadWallPhotoWithToken({ groupId: config.groupId, token: config.userToken, image, caption });
}

export async function postPhoto(config, { message, image, from_group = true, guid, publish_date }) {
  validatePublicVedicWayImageUrl(image);
  const photo = await uploadWallPhoto(config, { image, caption: message });
  const post = await callVk('wall.post', {
    owner_id: config.ownerId,
    message,
    from_group: from_group ? 1 : 0,
    attachments: photo.attachment,
    guid,
    publish_date: normalizePublishDate(publish_date),
  }, config.groupToken);
  return { ...post, attachment: photo.attachment, photo };
}

export function getWall(config, { count = 20, offset = 0 } = {}, vkApi = callVk) {
  return vkApi('wall.get', { owner_id: config.ownerId, count, offset }, config.userToken);
}
