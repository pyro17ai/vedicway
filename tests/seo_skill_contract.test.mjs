import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

test('production skills route cover and Pinterest generation through built-in Image Gen', () => {
  const create = read('.agents/skills/vedicway-create-image/SKILL.md');
  const createAgent = read('.agents/skills/vedicway-create-image/agents/openai.yaml');
  const cover = read('.agents/skills/vedicway-article-cover-image/SKILL.md');
  const pinterest = read('.agents/skills/vedicway-pinterest-card-image/SKILL.md');
  assert.match(create, /\$imagegen/);
  assert.match(create, /image_gen/);
  assert.match(create, /vedicway_import_generated_image/);
  assert.doesNotMatch(create, /vedicway-imagegen/);
  assert.doesNotMatch(createAgent, /vedicway-imagegen|OPENAI_API_KEY/);
  assert.match(cover, /kind=article-cover/);
  assert.match(pinterest, /kind=pinterest-card/);
  assert.match(cover, /source_kind=generated/);
  assert.match(pinterest, /source_kind=generated/);
  assert.doesNotMatch(`${cover}\n${pinterest}`, /source_kind=ai-generated/);
});

test('content brief consumes persisted research returned by the cluster claim', () => {
  const brief = read('.agents/skills/vedicway-content-brief/SKILL.md');
  assert.match(brief, /primary_query/);
  assert.match(brief, /serp_snapshots/);
  assert.match(brief, /Не вызывай Yandex MCP/);
});

test('ledger computes canonical content fingerprints instead of asking Codex to guess them', () => {
  const signals = read('.agents/skills/vedicway-yandex-signals/SKILL.md');
  const brief = read('.agents/skills/vedicway-content-brief/SKILL.md');
  const writer = read('.agents/skills/vedicway-article-writer/SKILL.md');
  assert.match(signals, /checksum` не передавай/);
  assert.match(brief, /без поля `checksum`/);
  assert.match(writer, /без поля `content_hash`/);
});

test('site publication reuses the media returned by the draft claim', () => {
  const publisher = read('.agents/skills/vedicway-site-publisher/SKILL.md');
  const media = read('.agents/skills/vedicway-article-media/SKILL.md');
  assert.match(publisher, /article\.content_markdown/);
  assert.doesNotMatch(publisher, /article\.content_html/);
  assert.match(media, /При `claim draft` сначала проверь массив `media`/);
  assert.match(media, /без новых вызовов Image Gen/);
});

test('publisher skills do not call removed control responsibilities', () => {
  const skills = [
    read('.agents/skills/vedicway-article-media/SKILL.md'),
    read('.agents/skills/vedicway-article-quality-gate/SKILL.md'),
    read('.agents/skills/vedicway-pinterest-publisher/SKILL.md'),
    read('.agents/skills/vedicway-vk-publisher/SKILL.md'),
  ].join('\n');
  for (const name of [
    'vedicway_generate_cover',
    'vedicway_generate_pinterest_card',
    'vedicway_quality_gate',
    'vedicway_build_distribution',
    'vedicway_verify_distribution',
  ]) assert.doesNotMatch(skills, new RegExp(name));
});
