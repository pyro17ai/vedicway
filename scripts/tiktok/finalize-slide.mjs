#!/usr/bin/env node
import path from 'node:path';

import { finalizeSlide } from './publisher-core.mjs';

function argument(name) {
  const index = process.argv.indexOf(name);
  const value = index >= 0 ? process.argv[index + 1] : null;
  if (!value || value.startsWith('--')) throw new Error(`${name} is required`);
  return value;
}

try {
  const result = await finalizeSlide({
    dataRoot: path.resolve('runtime/tiktok'),
    sourcePath: path.resolve(argument('--source')),
    outputPath: path.resolve(argument('--output')),
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
}
