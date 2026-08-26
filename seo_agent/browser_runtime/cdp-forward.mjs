#!/usr/bin/env node
import net from 'node:net';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

function validPort(value, { allowZero = false } = {}) {
  return Number.isInteger(value) && value >= (allowZero ? 0 : 1) && value <= 65535;
}

export function createCdpForwarder({
  targetHost = '127.0.0.1',
  targetPort,
  listenHost = '0.0.0.0',
  listenPort,
}) {
  if (!validPort(targetPort) || !validPort(listenPort, { allowZero: true })) {
    throw new Error('CDP target and proxy ports must be valid TCP ports');
  }
  const server = net.createServer(client => {
    const upstream = net.createConnection({ host: targetHost, port: targetPort });
    let headerBuffer = Buffer.alloc(0);
    let forwarding = false;
    const closeBoth = () => {
      client.destroy();
      upstream.destroy();
    };
    client.once('error', closeBoth);
    upstream.once('error', closeBoth);
    client.pause();
    upstream.once('connect', () => {
      upstream.pipe(client);
      const forwardRequest = chunk => {
        headerBuffer = Buffer.concat([headerBuffer, chunk]);
        if (headerBuffer.length > 65536) {
          closeBoth();
          return;
        }
        const headerEnd = headerBuffer.indexOf('\r\n\r\n');
        if (headerEnd === -1) return;
        const requestEnd = headerEnd + 4;
        const requestHead = headerBuffer.subarray(0, requestEnd).toString('latin1');
        if (!/^Host:[^\r\n]*$/im.test(requestHead)) {
          closeBoth();
          return;
        }
        const rewrittenHead = requestHead.replace(
          /^Host:[^\r\n]*$/im,
          `Host: ${targetHost}:${targetPort}`,
        );
        forwarding = true;
        client.removeListener('data', forwardRequest);
        upstream.write(Buffer.from(rewrittenHead, 'latin1'));
        if (headerBuffer.length > requestEnd) {
          upstream.write(headerBuffer.subarray(requestEnd));
        }
        headerBuffer = Buffer.alloc(0);
        client.pipe(upstream);
      };
      client.on('data', forwardRequest);
      client.resume();
    });
    client.once('end', () => {
      if (!forwarding) upstream.end();
    });
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(listenPort, listenHost, () => {
      server.removeListener('error', reject);
      resolve(server);
    });
  });
}

export async function main() {
  const targetPort = Number(process.env.VEDICWAY_BROWSER_CDP_PORT);
  const listenPort = Number(process.env.VEDICWAY_BROWSER_CDP_PROXY_PORT);
  if (!validPort(targetPort) || !validPort(listenPort)) {
    throw new Error('VEDICWAY_BROWSER_CDP_PORT and VEDICWAY_BROWSER_CDP_PROXY_PORT are required');
  }
  const server = await createCdpForwarder({ targetPort, listenPort });
  process.stdout.write(`${JSON.stringify({ status: 'forwarding', targetPort, listenPort })}\n`);
  const shutdown = () => server.close(() => process.exit(0));
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
