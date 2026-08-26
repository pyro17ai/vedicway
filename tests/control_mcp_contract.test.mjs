import assert from 'node:assert/strict';
import test from 'node:test';

import * as controlMcp from '../seo_agent/mcp/packages/agent-control-mcp/src/index.mjs';

const { executeToolCall, toolDefinitions } = controlMcp;

const expectedTools = [
  'vedicway_ledger_health',
  'vedicway_ledger_due_lifecycle',
  'vedicway_ledger_claim',
  'vedicway_claim_pinterest_batch',
  'vedicway_ledger_write',
  'vedicway_import_generated_image',
  'vedicway_stage_dzen_media',
  'vedicway_build_pinterest_csv',
  'vedicway_record_run_log',
  'vedicway_record_result',
  'vedicway_publish_site',
];

test('control MCP exposes only narrow VedicWay operations', () => {
  assert.deepEqual(toolDefinitions.map((tool) => tool.name), expectedTools);
  for (const tool of toolDefinitions) {
    assert.equal(tool.inputSchema.additionalProperties, false);
  }
});

test('control MCP narrows claims and ledger payloads to the active job', () => {
  assert.equal(typeof controlMcp.toolDefinitionsForJob, 'function');
  if (typeof controlMcp.toolDefinitionsForJob !== 'function') return;
  const definitions = controlMcp.toolDefinitionsForJob('article_site_publish');
  const claim = definitions.find((tool) => tool.name === 'vedicway_ledger_claim');
  assert.deepEqual(claim.inputSchema.properties.entity.enum, ['draft']);
  const write = definitions.find((tool) => tool.name === 'vedicway_ledger_write');
  const distributionItem = write.inputSchema.oneOf.find(
    (branch) => branch.properties.record_type.const === 'distribution-item',
  );
  assert.deepEqual(
    distributionItem.properties.payload.required,
    [
      'source_publication_id', 'platform', 'kind', 'title', 'body',
      'target_url', 'media_width', 'media_height', 'alt_text',
    ],
  );
  assert.equal(distributionItem.properties.payload.additionalProperties, false);
  assert.deepEqual(
    write.inputSchema.oneOf.map((branch) => branch.properties.record_type.const),
    ['publication-attempt', 'publication', 'distribution-item'],
  );
});

test('control MCP exposes deterministic Dzen cover staging only to the Dzen job', () => {
  assert.equal(typeof controlMcp.toolDefinitionsForJob, 'function');
  if (typeof controlMcp.toolDefinitionsForJob !== 'function') return;
  const dzen = controlMcp.toolDefinitionsForJob('dzen_daily_publish');
  const site = controlMcp.toolDefinitionsForJob('article_site_publish');
  assert.ok(dzen.some((tool) => tool.name === 'vedicway_stage_dzen_media'));
  assert.ok(!site.some((tool) => tool.name === 'vedicway_stage_dzen_media'));
});

test('Pinterest job exposes one batch claim instead of repeatable single claims', () => {
  const pinterest = controlMcp.toolDefinitionsForJob('pinterest_daily_publish');
  assert.ok(pinterest.some((tool) => tool.name === 'vedicway_claim_pinterest_batch'));
  assert.ok(!pinterest.some((tool) => tool.name === 'vedicway_ledger_claim'));
});

test('control MCP publishes target-specific evidence requirements to Codex', () => {
  const publicationEvidence = (jobName) => {
    const definitions = controlMcp.toolDefinitionsForJob(jobName);
    const write = definitions.find((tool) => tool.name === 'vedicway_ledger_write');
    return write.inputSchema.oneOf.find(
      (branch) => branch.properties.record_type.const === 'publication',
    ).properties.payload.properties.evidence;
  };

  assert.deepEqual(
    publicationEvidence('article_site_publish').properties.checks.required,
    [
      'canonical', 'article_schema', 'title', 'request_hash', 'sitemap',
      'cover', 'all_media_public',
    ],
  );
  assert.deepEqual(
    publicationEvidence('dzen_daily_publish').properties.checks.required,
    ['editor_persisted', 'public_url_verified', 'playwright_ui', 'cover_present'],
  );
});

test('control MCP exposes the lifecycle queue as a read-only typed action', async () => {
  let observedAction;
  const response = await executeToolCall(
    { params: { name: 'vedicway_ledger_due_lifecycle', arguments: { limit: 7 } } },
    async (action) => {
      observedAction = action;
      return { code: 0, stdout: '{"items":[]}', stderr: '' };
    },
  );
  assert.equal(observedAction, 'ledger-due-lifecycle');
  assert.equal(response.isError, undefined);
});

test('control MCP imports a built-in Image Gen artifact through a typed action', async () => {
  const definition = toolDefinitions.find((tool) => tool.name === 'vedicway_import_generated_image');
  assert.deepEqual(definition.inputSchema.required, ['kind', 'output']);
  let observedAction;
  const response = await executeToolCall(
    {
      params: {
        name: 'vedicway_import_generated_image',
        arguments: {
          source_path: '/codex/generated_images/session/image.png',
          kind: 'pinterest-card',
          output: 'media/pinterest/card-01.webp',
        },
      },
    },
    async (action) => {
      observedAction = action;
      return { code: 0, stdout: '{"generator":"codex-imagegen"}', stderr: '' };
    },
  );
  assert.equal(observedAction, 'import-generated-image');
  assert.equal(response.isError, undefined);
});

test('control MCP can import the current run image when Image Gen omits its path', async () => {
  const response = await executeToolCall(
    {
      params: {
        name: 'vedicway_import_generated_image',
        arguments: {
          kind: 'article-cover',
          output: 'media/article/cover.webp',
        },
      },
    },
    async () => ({ code: 0, stdout: '{"generator":"codex-imagegen"}', stderr: '' }),
  );
  assert.equal(response.isError, undefined);
});

test('control MCP writes one short text log for the active run', async () => {
  const definition = toolDefinitions.find((tool) => tool.name === 'vedicway_record_run_log');
  assert.deepEqual(definition.inputSchema.required, ['log_text']);
  let observedAction;
  const response = await executeToolCall(
    {
      params: {
        name: 'vedicway_record_run_log',
        arguments: { log_text: 'Задача выполнена. Ошибок не возникло.' },
      },
    },
    async (action) => {
      observedAction = action;
      return { code: 0, stdout: '{"cron_run_id":"run-1"}', stderr: '' };
    },
  );
  assert.equal(observedAction, 'record-run-log');
  assert.equal(response.isError, undefined);
});

test('control MCP reports subprocess failures as MCP errors', async () => {
  const response = await executeToolCall(
    { params: { name: 'vedicway_ledger_health', arguments: {} } },
    async () => ({ code: 2, stdout: '', stderr: 'database unavailable' }),
  );
  assert.equal(response.isError, true);
  assert.match(response.content[0].text, /database unavailable/);
});

test('control MCP rejects names outside its fixed action map', async () => {
  const response = await executeToolCall(
    { params: { name: 'run_shell', arguments: { command: 'id' } } },
    async () => ({ code: 0, stdout: '{}', stderr: '' }),
  );
  assert.equal(response.isError, true);
  assert.match(response.content[0].text, /Unknown tool/);
});

test('control MCP does not treat the SDK request context as a runner', async () => {
  const originalExecutable = process.env.PYTHON_EXECUTABLE;
  process.env.PYTHON_EXECUTABLE = 'definitely-missing-python';
  try {
    const response = await executeToolCall(
      { params: { name: 'vedicway_ledger_health', arguments: {} } },
      { signal: new AbortController().signal },
    );
    assert.equal(response.isError, true);
    assert.doesNotMatch(response.content[0].text, /runner is not a function/);
  } finally {
    if (originalExecutable === undefined) delete process.env.PYTHON_EXECUTABLE;
    else process.env.PYTHON_EXECUTABLE = originalExecutable;
  }
});
