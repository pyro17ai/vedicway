import assert from 'node:assert/strict';
import test from 'node:test';
import sharp from '../seo_agent/mcp/node_modules/sharp/lib/index.js';

const moduleUrl = new URL(
  '../seo_agent/mcp/packages/vk-group-mcp/src/vk-client.js',
  import.meta.url,
);

async function loadClient() {
  try {
    return await import(moduleUrl);
  } catch (error) {
    assert.fail(`VK MCP client must load: ${error.message}`);
  }
}

test('VK config requires a user token for the photo upload leg', async () => {
  const { getConfig } = await loadClient();
  assert.throws(
    () => getConfig({ VK_GROUP_ID: '91234', VK_GROUP_ACCESS_TOKEN: 'group-token' }),
    /VK_USER_ACCESS_TOKEN/,
  );
  assert.deepEqual(
    getConfig({
      VK_GROUP_ID: '91234',
      VK_GROUP_ACCESS_TOKEN: 'group-token',
      VK_USER_ACCESS_TOKEN: 'user-token',
    }),
    {
      groupId: 91234,
      ownerId: -91234,
      groupToken: 'group-token',
      userToken: 'user-token',
    },
  );
});

test('VK scheduled publication accepts a timezone-aware ISO timestamp', async () => {
  const { normalizePublishDate } = await loadClient();
  assert.equal(normalizePublishDate('2026-08-19T12:00:00+03:00'), 1787130000);
});

test('VK photo publication accepts only public VedicWay article media', async () => {
  const { validatePublicVedicWayImageUrl } = await loadClient();
  assert.equal(
    validatePublicVedicWayImageUrl('https://vedicway.ru/media/articles/asset/1200.webp'),
    'https://vedicway.ru/media/articles/asset/1200.webp',
  );
  assert.throws(() => validatePublicVedicWayImageUrl('/run/secrets/token.webp'), /VedicWay article media/);
  assert.throws(() => validatePublicVedicWayImageUrl('http://vedicway.ru/media/articles/a/1200.webp'), /VedicWay article media/);
  assert.throws(() => validatePublicVedicWayImageUrl('https://evil.example/a.webp'), /VedicWay article media/);
});

test('VK photo upload always transcodes article WebP to a JPEG multipart file', async () => {
  const { normalizeVkPhoto } = await loadClient();
  const webp = await sharp({
    create: { width: 8, height: 8, channels: 3, background: '#2f1f4a' },
  }).webp().toBuffer();

  const normalized = await normalizeVkPhoto(webp);
  const bytes = new Uint8Array(await normalized.blob.arrayBuffer());

  assert.equal(normalized.filename, 'photo.jpg');
  assert.equal(normalized.blob.type, 'image/jpeg');
  assert.deepEqual([...bytes.slice(0, 2)], [0xff, 0xd8]);
});

test('VK photo upload retries with a fresh upload server after an empty photo response', async () => {
  const { uploadWallPhoto } = await loadClient();
  const webp = await sharp({
    create: { width: 8, height: 8, channels: 3, background: '#2f1f4a' },
  }).webp().toBuffer();
  const originalFetch = globalThis.fetch;
  let uploadServerCalls = 0;
  let uploadCalls = 0;
  let imageCalls = 0;

  globalThis.fetch = async (input) => {
    const url = String(input);
    if (url === 'https://vedicway.ru/media/articles/asset/1200.webp') {
      imageCalls += 1;
      return new Response(webp, { headers: { 'content-type': 'image/webp' } });
    }
    if (url.endsWith('/photos.getWallUploadServer')) {
      uploadServerCalls += 1;
      return Response.json({ response: { upload_url: `https://upload.vk/${uploadServerCalls}` } });
    }
    if (url.startsWith('https://upload.vk/')) {
      uploadCalls += 1;
      return Response.json({
        server: uploadCalls,
        photo: uploadCalls === 1 ? '' : '[{"photo":"ok"}]',
        hash: `hash-${uploadCalls}`,
      });
    }
    if (url.endsWith('/photos.saveWallPhoto')) {
      return Response.json({ response: [{ owner_id: -91234, id: 77 }] });
    }
    throw new Error(`Unexpected URL: ${url}`);
  };

  try {
    const photo = await uploadWallPhoto(
      { groupId: 91234, userToken: 'user-token' },
      {
        image: 'https://vedicway.ru/media/articles/asset/1200.webp',
        caption: 'Проверка',
      },
    );
    assert.equal(photo.attachment, 'photo-91234_77');
    assert.equal(uploadServerCalls, 2);
    assert.equal(uploadCalls, 2);
    assert.equal(imageCalls, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('VK photo upload retries a transient upload-server HTTP failure', async () => {
  const { uploadWallPhoto } = await loadClient();
  const webp = await sharp({
    create: { width: 8, height: 8, channels: 3, background: '#2f1f4a' },
  }).webp().toBuffer();
  const originalFetch = globalThis.fetch;
  let uploadServerCalls = 0;
  let uploadCalls = 0;

  globalThis.fetch = async (input) => {
    const url = String(input);
    if (url === 'https://vedicway.ru/media/articles/asset/1200.webp') {
      return new Response(webp, { headers: { 'content-type': 'image/webp' } });
    }
    if (url.endsWith('/photos.getWallUploadServer')) {
      uploadServerCalls += 1;
      return Response.json({ response: { upload_url: `https://upload.vk/${uploadServerCalls}` } });
    }
    if (url.startsWith('https://upload.vk/')) {
      uploadCalls += 1;
      if (uploadCalls === 1) return new Response('', { status: 502 });
      return Response.json({ server: 2, photo: '[{"photo":"ok"}]', hash: 'hash-2' });
    }
    if (url.endsWith('/photos.saveWallPhoto')) {
      return Response.json({ response: [{ owner_id: -91234, id: 78 }] });
    }
    throw new Error(`Unexpected URL: ${url}`);
  };

  try {
    const photo = await uploadWallPhoto(
      { groupId: 91234, userToken: 'user-token' },
      {
        image: 'https://vedicway.ru/media/articles/asset/1200.webp',
        caption: 'Проверка',
      },
    );
    assert.equal(photo.attachment, 'photo-91234_78');
    assert.equal(uploadServerCalls, 2);
    assert.equal(uploadCalls, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('VK wall verification uses the user token accepted by wall.get', async () => {
  const { getWall } = await loadClient();
  const expected = { count: 1, items: [{ id: 77, owner_id: -91234 }] };
  const config = {
    groupId: 91234,
    ownerId: -91234,
    groupToken: 'group-token',
    userToken: 'user-token',
  };
  const vkApi = async (method, params, token) => {
    if (token !== 'user-token') {
      throw new Error('VK API Error 27: method is unavailable with group auth');
    }
    assert.equal(method, 'wall.get');
    assert.deepEqual(params, { owner_id: -91234, count: 1, offset: 0 });
    return expected;
  };

  assert.deepEqual(await getWall(config, { count: 1 }, vkApi), expected);
});
