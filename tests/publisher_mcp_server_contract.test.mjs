import assert from 'node:assert/strict';
import test from 'node:test';

async function load(relativePath, label) {
  try {
    return await import(new URL(relativePath, import.meta.url));
  } catch (error) {
    assert.fail(`${label} MCP server must load: ${error.message}`);
  }
}

test('VK MCP exposes only photo publishing and wall verification', async () => {
  const { toolDefinitions } = await load(
    '../seo_agent/mcp/packages/vk-group-mcp/src/index.js',
    'VK',
  );
  assert.deepEqual(
    toolDefinitions.map((tool) => tool.name),
    ['vk_group_post_photo', 'vk_group_get_wall'],
  );
});

test('publisher MCP servers reject unknown tool names', async () => {
  const vk = await load('../seo_agent/mcp/packages/vk-group-mcp/src/index.js', 'VK');
  await assert.rejects(() => vk.handleToolCall('unknown', {}, {}), /Unknown tool/);
});

test('publisher MCP servers mark tool failures as MCP errors', async () => {
  const vk = await load('../seo_agent/mcp/packages/vk-group-mcp/src/index.js', 'VK');
  const vkFailure = await vk.executeToolCall({ params: { name: 'unknown', arguments: {} } });
  assert.equal(vkFailure.isError, true);
  assert.match(vkFailure.content[0].text, /Unknown tool/);
});
