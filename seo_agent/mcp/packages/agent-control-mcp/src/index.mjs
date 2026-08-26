#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';

const recordTypes = [
  'source-document', 'tool-response', 'query', 'cluster', 'brief', 'draft',
  'serp-snapshot', 'draft-quality', 'media', 'publication-attempt', 'publication',
  'performance', 'action', 'action-result', 'distribution-item',
  'distribution-attempt', 'distribution-publication',
];

const objectSchema = { type: 'object' };

const text = (extra = {}) => ({ type: 'string', minLength: 1, ...extra });
const optionalText = (extra = {}) => ({ type: 'string', ...extra });
const stringArray = { type: 'array', items: text(), minItems: 1, uniqueItems: true };

function recordPayload(required, properties) {
  return {
    type: 'object',
    properties: { id: optionalText(), ...properties },
    required,
    additionalProperties: false,
  };
}

const recordPayloadSchemas = {
  'source-document': recordPayload(
    ['source_kind', 'source_key', 'checksum'],
    {
      source_kind: { enum: ['web', 'mcp', 'repository', 'editorial'] },
      source_key: text(),
      checksum: text(),
      url: optionalText(),
      status: { enum: ['active', 'stale', 'rejected'] },
      retrieved_at: optionalText(),
      payload: objectSchema,
    },
  ),
  'tool-response': recordPayload(
    ['provider', 'tool_name', 'request_hash', 'response'],
    {
      cron_run_id: optionalText(),
      provider: {
        enum: [
          'yandex-search', 'wordstat', 'webmaster', 'metrika',
          'site', 'dzen', 'vk', 'pinterest',
        ],
      },
      tool_name: text(),
      request_hash: text(),
      response: objectSchema,
      observed_at: optionalText(),
      expires_at: optionalText(),
    },
  ),
  query: recordPayload(
    ['phrase', 'region_id', 'source', 'raw_response_id'],
    {
      phrase: text(),
      region_id: text(),
      source: { enum: ['wordstat', 'webmaster', 'metrika'] },
      intent: { enum: ['informational', 'commercial', 'navigational'] },
      metrics: objectSchema,
      observed_at: optionalText(),
      raw_response_id: text(),
    },
  ),
  'serp-snapshot': recordPayload(
    ['query_id', 'region_id', 'results', 'raw_response_id'],
    {
      query_id: text(),
      region_id: text(),
      results: { type: 'array', items: objectSchema, minItems: 1 },
      raw_response_id: text(),
      requested_at: optionalText(),
    },
  ),
  cluster: recordPayload(
    ['slug', 'title', 'intent', 'status', 'query_ids', 'primary_query_id'],
    {
      slug: text(),
      title: text(),
      intent: { enum: ['informational', 'commercial', 'navigational'] },
      status: { const: 'ready' },
      priority_score: { type: 'number' },
      rationale: optionalText(),
      query_ids: stringArray,
      primary_query_id: text(),
    },
  ),
  brief: recordPayload(
    [
      'cluster_id', 'claim_token', 'title', 'primary_query', 'audience_problem',
      'search_intent', 'outline', 'evidence', 'internal_links', 'prohibited_claims',
    ],
    {
      cluster_id: text(),
      claim_token: text(),
      title: text(),
      primary_query: text(),
      audience_problem: text(),
      search_intent: text(),
      outline: { type: 'array', items: text(), minItems: 4, maxItems: 8 },
      evidence: { type: 'array', items: {}, minItems: 2 },
      internal_links: { type: 'array', items: text(), minItems: 2 },
      prohibited_claims: { type: 'array', items: text(), minItems: 1 },
    },
  ),
  draft: recordPayload(
    [
      'brief_id', 'slug', 'title', 'excerpt', 'content_markdown', 'seo_title',
      'meta_description', 'focus_keyphrase', 'category',
    ],
    {
      brief_id: text(),
      slug: text(),
      title: text(),
      excerpt: text(),
      content_markdown: text(),
      seo_title: text(),
      meta_description: text(),
      focus_keyphrase: text(),
      category: text(),
      author_name: optionalText(),
      status: { enum: ['draft', 'editing'] },
      action_id: optionalText(),
      action_claim_token: optionalText(),
    },
  ),
  'draft-quality': recordPayload(
    ['draft_id', 'passed', 'report'],
    { draft_id: text(), passed: { type: 'boolean' }, report: objectSchema },
  ),
  media: recordPayload(
    [
      'draft_id', 'purpose', 'local_path', 'alt_text', 'source_kind',
      'license_note', 'checksum',
    ],
    {
      draft_id: text(),
      purpose: { enum: ['cover', 'body'] },
      local_path: text(),
      alt_text: text(),
      title: optionalText(),
      caption: optionalText(),
      source_kind: { enum: ['generated', 'licensed', 'owned'] },
      source_url: optionalText(),
      license_note: text(),
      checksum: text(),
      backend_media_id: optionalText(),
      public_url: optionalText(),
      distribution_role: { const: 'pinterest' },
    },
  ),
  'publication-attempt': recordPayload(
    [
      'draft_id', 'target', 'idempotency_key', 'attempt_token', 'status',
      'content_hash', 'request_hash', 'response',
    ],
    {
      draft_id: text(),
      target: { enum: ['site', 'dzen'] },
      claim_token: optionalText(),
      idempotency_key: text(),
      attempt_token: text(),
      status: { enum: ['succeeded', 'failed', 'blocked'] },
      content_hash: text(),
      request_hash: text(),
      response: objectSchema,
      attempt_no: { type: 'integer', minimum: 1 },
      started_at: optionalText(),
    },
  ),
  publication: recordPayload(
    [
      'draft_id', 'target', 'public_url', 'content_hash', 'request_hash',
      'attempt_token', 'evidence',
    ],
    {
      draft_id: text(),
      target: { enum: ['site', 'dzen'] },
      claim_token: optionalText(),
      public_url: text(),
      external_id: optionalText(),
      content_hash: text(),
      request_hash: text(),
      attempt_token: text(),
      evidence: objectSchema,
      status: { enum: ['published', 'verified'] },
      published_at: optionalText(),
    },
  ),
  performance: recordPayload(
    ['publication_id', 'window_start', 'window_end', 'webmaster', 'metrika'],
    {
      publication_id: text(),
      window_start: text(),
      window_end: text(),
      webmaster: objectSchema,
      metrika: objectSchema,
      captured_at: optionalText(),
    },
  ),
  action: recordPayload(
    ['publication_id', 'action_type', 'hypothesis', 'success_metric', 'evidence'],
    {
      publication_id: text(),
      action_type: {
        enum: ['rewrite', 'expand', 'internal_links', 'title_test', 'recrawl', 'hold'],
      },
      priority_score: { type: 'number' },
      hypothesis: text(),
      success_metric: text(),
      evidence: objectSchema,
    },
  ),
  'action-result': recordPayload(
    ['action_id', 'claim_token', 'status', 'evidence'],
    {
      action_id: text(),
      claim_token: text(),
      status: { enum: ['completed', 'rejected'] },
      evidence: objectSchema,
    },
  ),
  'distribution-item': recordPayload(
    [
      'source_publication_id', 'platform', 'kind', 'title', 'body',
      'target_url', 'media_width', 'media_height', 'alt_text',
    ],
    {
      source_publication_id: text(),
      platform: { enum: ['vk', 'pinterest'] },
      kind: { enum: ['article_digest', 'astrology_card'] },
      title: text(),
      body: text(),
      target_url: text(),
      media_id: optionalText(),
      media_role: { enum: ['cover', 'pinterest'] },
      media_width: { type: 'integer', minimum: 1 },
      media_height: { type: 'integer', minimum: 1 },
      alt_text: text(),
      metadata: objectSchema,
    },
  ),
  'distribution-attempt': recordPayload(
    [
      'item_id', 'claim_token', 'attempt_token', 'idempotency_key', 'status',
      'request_hash', 'response',
    ],
    {
      item_id: text(),
      claim_token: text(),
      attempt_token: text(),
      idempotency_key: text(),
      status: { enum: ['succeeded', 'failed', 'blocked'] },
      request_hash: text(),
      response: objectSchema,
      external_id: optionalText(),
      external_url: optionalText(),
    },
  ),
  'distribution-publication': recordPayload(
    [
      'item_id', 'claim_token', 'attempt_token', 'request_hash', 'external_id',
      'external_url', 'evidence',
    ],
    {
      item_id: text(),
      claim_token: text(),
      attempt_token: text(),
      request_hash: text(),
      external_id: text(),
      external_url: text(),
      evidence: objectSchema,
    },
  ),
};

function ledgerWriteBranch(recordType) {
  return {
    type: 'object',
    properties: {
      record_type: { const: recordType },
      payload: recordPayloadSchemas[recordType],
    },
    required: ['record_type', 'payload'],
    additionalProperties: false,
  };
}

const ledgerWriteInputSchema = {
  type: 'object',
  properties: {
    record_type: { enum: recordTypes },
    payload: objectSchema,
  },
  required: ['record_type', 'payload'],
  additionalProperties: false,
  oneOf: recordTypes.map(ledgerWriteBranch),
};

export const toolDefinitions = [
  {
    name: 'vedicway_ledger_health',
    description: 'Initialize the VedicWay SEO schema and return ledger health',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'vedicway_ledger_due_lifecycle',
    description: 'Read the due VedicWay site publications for the active lifecycle-review run',
    inputSchema: {
      type: 'object',
      properties: { limit: { type: 'integer', minimum: 1, maximum: 100 } },
      additionalProperties: false,
    },
  },
  {
    name: 'vedicway_ledger_claim',
    description: 'Claim one entity allowed for the active scheduler run',
    inputSchema: {
      type: 'object',
      properties: {
        entity: { enum: ['cluster', 'draft', 'dzen-article', 'action', 'vk-post', 'pinterest-pin'] },
        lease_seconds: { type: 'integer', minimum: 30, maximum: 86400 },
      },
      required: ['entity'],
      additionalProperties: false,
    },
  },
  {
    name: 'vedicway_claim_pinterest_batch',
    description: 'Claim up to ten Pinterest items for the active run in order, stopping immediately after the first empty queue result',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'vedicway_ledger_write',
    description: 'Write one contract-validated record owned by the active run',
    inputSchema: {
      type: 'object',
      properties: {
        record_type: { enum: recordTypes },
        payload: objectSchema,
      },
      ...ledgerWriteInputSchema,
    },
  },
  {
    name: 'vedicway_import_generated_image',
    description: 'Import one built-in Codex Image Gen artifact into VedicWay-owned media storage. Omit source_path when the built-in tool does not return it; the control imports the newest unconsumed artifact created by this scheduler run.',
    inputSchema: {
      type: 'object',
      properties: {
        source_path: { type: 'string', minLength: 1, maxLength: 2000 },
        kind: { enum: ['article-cover', 'pinterest-card'] },
        output: { type: 'string', minLength: 6, maxLength: 1000, pattern: '\\.webp$' },
      },
      required: ['kind', 'output'],
      additionalProperties: false,
    },
  },
  {
    name: 'vedicway_stage_dzen_media',
    description: 'Stage the owned cover of the article claimed by the active Dzen run into its Playwright workspace',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'vedicway_build_pinterest_csv',
    description: 'Build one deterministic Pinterest CSV from the ten items claimed by the active run',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'vedicway_record_run_log',
    description: 'Write one short plain-text execution log for the active scheduler run',
    inputSchema: {
      type: 'object',
      properties: {
        log_text: { type: 'string', minLength: 1, maxLength: 4000 },
      },
      required: ['log_text'],
      additionalProperties: false,
    },
  },
  {
    name: 'vedicway_record_result',
    description: 'Record the single terminal result: completed only after all claimed entities reach their verified terminal state; use blocked after a failed or blocked external attempt',
    inputSchema: {
      type: 'object',
      properties: {
        outcome: { enum: ['completed', 'blocked', 'skipped'] },
        summary: { type: 'string', minLength: 1, maxLength: 2000 },
        artifact: objectSchema,
      },
      required: ['outcome', 'summary'],
      additionalProperties: false,
    },
  },
  {
    name: 'vedicway_publish_site',
    description: 'Validate, dry-run, publish and publicly verify one claimed VedicWay blog manifest',
    inputSchema: {
      type: 'object',
      properties: { manifest: objectSchema },
      required: ['manifest'],
      additionalProperties: false,
    },
  },
];

const claimsByJob = {
  article_content_production: ['cluster'],
  article_site_publish: ['draft'],
  dzen_daily_publish: ['dzen-article'],
  article_optimization: ['action', 'draft'],
  vk_daily_publish: ['vk-post'],
};

const recordsByJob = {
  article_intelligence_refresh: [
    'source-document', 'tool-response', 'query', 'serp-snapshot', 'cluster',
  ],
  article_content_production: ['brief', 'draft', 'draft-quality', 'media'],
  article_site_publish: [
    'publication-attempt', 'publication', 'distribution-item',
  ],
  dzen_daily_publish: ['publication-attempt', 'publication'],
  vk_daily_publish: [
    'tool-response', 'distribution-attempt', 'distribution-publication',
  ],
  pinterest_daily_publish: [
    'distribution-attempt', 'distribution-publication',
  ],
  article_optimization: [
    'draft', 'draft-quality', 'media', 'publication-attempt', 'publication',
    'action-result',
  ],
  article_lifecycle_review: ['tool-response', 'performance', 'action'],
};

const extraToolsByJob = {
  article_content_production: ['vedicway_import_generated_image'],
  article_site_publish: ['vedicway_publish_site'],
  dzen_daily_publish: ['vedicway_stage_dzen_media'],
  pinterest_daily_publish: [
    'vedicway_claim_pinterest_batch', 'vedicway_build_pinterest_csv',
  ],
  article_optimization: ['vedicway_import_generated_image', 'vedicway_publish_site'],
  article_lifecycle_review: ['vedicway_ledger_due_lifecycle'],
};

export function toolDefinitionsForJob(jobName) {
  const recordTypesForJob = recordsByJob[jobName];
  if (!recordTypesForJob) return toolDefinitions;
  const allowedTools = new Set([
    'vedicway_ledger_health', 'vedicway_ledger_write', 'vedicway_record_run_log',
    'vedicway_record_result', ...(extraToolsByJob[jobName] || []),
  ]);
  const claimEntities = claimsByJob[jobName];
  if (claimEntities) allowedTools.add('vedicway_ledger_claim');
  const definitions = JSON.parse(JSON.stringify(
    toolDefinitions.filter((tool) => allowedTools.has(tool.name)),
  ));
  const claim = definitions.find((tool) => tool.name === 'vedicway_ledger_claim');
  if (claim) claim.inputSchema.properties.entity.enum = claimEntities;
  const write = definitions.find((tool) => tool.name === 'vedicway_ledger_write');
  write.inputSchema.properties.record_type.enum = recordTypesForJob;
  write.inputSchema.oneOf = write.inputSchema.oneOf.filter(
    (branch) => recordTypesForJob.includes(branch.properties.record_type.const),
  );
  const siteTarget = ['article_site_publish', 'article_optimization'].includes(jobName);
  const dzenTarget = jobName === 'dzen_daily_publish';
  if (siteTarget || dzenTarget) {
    for (const branch of write.inputSchema.oneOf) {
      if (!['publication-attempt', 'publication'].includes(
        branch.properties.record_type.const,
      )) continue;
      const payload = branch.properties.payload;
      payload.properties.target.enum = [siteTarget ? 'site' : 'dzen'];
      if (siteTarget && !payload.required.includes('claim_token')) {
        payload.required.push('claim_token');
      }
      if (branch.properties.record_type.const === 'publication') {
        const requiredChecks = siteTarget
          ? [
            'canonical', 'article_schema', 'title', 'request_hash', 'sitemap',
            'cover', 'all_media_public',
          ]
          : ['editor_persisted', 'public_url_verified', 'playwright_ui', 'cover_present'];
        payload.properties.evidence = {
          type: 'object',
          properties: {
            checks: {
              type: 'object',
              properties: Object.fromEntries(
                requiredChecks.map((name) => [name, { const: true }]),
              ),
              required: requiredChecks,
              additionalProperties: true,
            },
            ...(siteTarget ? { page_sha256: text(), sitemap_sha256: text() } : {}),
          },
          required: siteTarget
            ? ['checks', 'page_sha256', 'sitemap_sha256']
            : ['checks'],
          additionalProperties: true,
        };
      }
    }
  }
  return definitions;
}

const actionByTool = new Map([
  ['vedicway_ledger_health', 'ledger-health'],
  ['vedicway_ledger_due_lifecycle', 'ledger-due-lifecycle'],
  ['vedicway_ledger_claim', 'ledger-claim'],
  ['vedicway_claim_pinterest_batch', 'ledger-claim-pinterest-batch'],
  ['vedicway_ledger_write', 'ledger-write'],
  ['vedicway_import_generated_image', 'import-generated-image'],
  ['vedicway_stage_dzen_media', 'stage-dzen-media'],
  ['vedicway_build_pinterest_csv', 'build-pinterest-csv'],
  ['vedicway_record_run_log', 'record-run-log'],
  ['vedicway_record_result', 'record-result'],
  ['vedicway_publish_site', 'publish-site'],
]);

function runControl(action, args) {
  return new Promise((resolve) => {
    const executable = process.env.PYTHON_EXECUTABLE || 'python';
    const child = spawn(executable, ['-m', 'seo_agent.control', action], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: process.env,
      windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    let exceeded = false;
    const append = (current, chunk) => {
      const next = current + chunk.toString('utf8');
      if (next.length > 2_000_000) {
        exceeded = true;
        child.kill();
      }
      return next.slice(0, 2_000_000);
    };
    child.stdout.on('data', (chunk) => { stdout = append(stdout, chunk); });
    child.stderr.on('data', (chunk) => { stderr = append(stderr, chunk); });
    child.on('error', (error) => resolve({ code: 2, stdout, stderr: error.message }));
    child.on('close', (code) => resolve({
      code: exceeded ? 2 : (code ?? 2),
      stdout,
      stderr: exceeded ? 'Control response exceeded 2 MB' : stderr,
    }));
    child.stdin.end(JSON.stringify(args || {}));
  });
}

function result(value, isError = false) {
  return {
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    ...(isError ? { isError: true } : {}),
  };
}

export async function executeToolCall(request, contextOrRunner) {
  try {
    const action = actionByTool.get(request.params.name);
    if (!action) throw new Error(`Unknown tool: ${request.params.name}`);
    const runner = typeof contextOrRunner === 'function' ? contextOrRunner : runControl;
    const execution = await runner(action, request.params.arguments || {});
    let parsed;
    try {
      parsed = execution.stdout ? JSON.parse(execution.stdout) : null;
    } catch {
      parsed = null;
    }
    if (execution.code !== 0) {
      const message = parsed?.error || execution.stderr.trim() || 'Control action failed';
      throw new Error(message.slice(0, 2000));
    }
    if (!parsed || typeof parsed !== 'object') throw new Error('Control returned invalid JSON');
    return result(parsed);
  } catch (error) {
    return result({ error: error instanceof Error ? error.message : 'Control action failed' }, true);
  }
}

export function createServer() {
  const server = new Server(
    { name: 'vedicway-agent-control-mcp', version: '1.0.0' },
    { capabilities: { tools: {} } },
  );
  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: toolDefinitionsForJob(process.env.VEDICWAY_SEO_JOB_NAME),
  }));
  server.setRequestHandler(CallToolRequestSchema, executeToolCall);
  return server;
}

export async function main() {
  await createServer().connect(new StdioServerTransport());
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : 'Control MCP failed');
    process.exit(1);
  });
}
