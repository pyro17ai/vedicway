import assert from 'node:assert/strict';
import http from 'node:http';
import test from 'node:test';

import { createCdpForwarder } from '../seo_agent/browser_runtime/cdp-forward.mjs';

const listen = (server, host = '127.0.0.1') => new Promise((resolve, reject) => {
  server.once('error', reject);
  server.listen(0, host, () => resolve(server.address()));
});

const close = (server) => new Promise((resolve, reject) => {
  server.close(error => error ? reject(error) : resolve());
});

test('CDP forwarder exposes Chromium privately and rewrites the DevTools Host header', async () => {
  let observedHost;
  const target = http.createServer((request, response) => {
    observedHost = request.headers.host;
    response.end('vedicway-cdp');
  });
  const targetAddress = await listen(target);
  const proxy = await createCdpForwarder({
    targetHost: '127.0.0.1',
    targetPort: targetAddress.port,
    listenHost: '127.0.0.1',
    listenPort: 0,
  });
  const proxyAddress = proxy.address();

  const body = await new Promise((resolve, reject) => {
    const request = http.get({
      host: '127.0.0.1',
      port: proxyAddress.port,
      headers: {
        Host: 'vedicway-seo-browser-pinterest:9325',
        Connection: 'close',
      },
    }, response => {
      const chunks = [];
      response.on('data', chunk => chunks.push(chunk));
      response.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    });
    request.once('error', reject);
  });

  await close(proxy);
  await close(target);
  assert.equal(body, 'vedicway-cdp');
  assert.equal(observedHost, `127.0.0.1:${targetAddress.port}`);
});
