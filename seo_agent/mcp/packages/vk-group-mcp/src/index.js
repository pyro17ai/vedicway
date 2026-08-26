#!/usr/bin/env node
import { fileURLToPath } from 'node:url';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { getConfig, getWall, postPhoto } from './vk-client.js';

export const toolDefinitions = [
  {
    name: 'vk_group_post_photo',
    description: 'Publish one VedicWay VK wall post with an image',
    inputSchema: {
      type: 'object',
      properties: {
        message: { type: 'string' },
        image: { type: 'string', description: 'Public VedicWay article-media HTTPS URL' },
        from_group: { type: 'boolean', default: true },
        guid: { type: 'string', description: 'Stable idempotency key' },
        publish_date: { oneOf: [{ type: 'integer' }, { type: 'string' }] },
      },
      required: ['message', 'image', 'guid'],
    },
  },
  {
    name: 'vk_group_get_wall',
    description: 'Read recent posts from the configured VedicWay VK community wall',
    inputSchema: {
      type: 'object',
      properties: {
        count: { type: 'integer', default: 20, minimum: 1, maximum: 100 },
        offset: { type: 'integer', default: 0, minimum: 0 },
      },
    },
  },
];

export async function handleToolCall(name, args, config = getConfig()) {
  if (name === 'vk_group_post_photo') return postPhoto(config, args);
  if (name === 'vk_group_get_wall') return getWall(config, args);
  throw new Error(`Unknown tool: ${name}`);
}

function result(value, isError = false) {
  return { content: [{ type: 'text', text: JSON.stringify(value, null, 2) }], ...(isError ? { isError: true } : {}) };
}

export async function executeToolCall(request) {
  try {
    if (!toolDefinitions.some((tool) => tool.name === request.params.name)) {
      throw new Error(`Unknown tool: ${request.params.name}`);
    }
    return result(await handleToolCall(request.params.name, request.params.arguments || {}));
  } catch (error) {
    return result({ error: error instanceof Error ? error.message : 'VK tool failed' }, true);
  }
}

export function createServer() {
  const server = new Server({ name: 'vedicway-vk-group-mcp', version: '1.0.0' }, { capabilities: { tools: {} } });
  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: toolDefinitions }));
  server.setRequestHandler(CallToolRequestSchema, executeToolCall);
  return server;
}

export async function main() {
  await createServer().connect(new StdioServerTransport());
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
