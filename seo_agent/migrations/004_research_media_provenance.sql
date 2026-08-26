ALTER TABLE raw_tool_responses
DROP CONSTRAINT raw_tool_responses_provider_check;

ALTER TABLE raw_tool_responses
ADD CONSTRAINT raw_tool_responses_provider_check
CHECK (provider IN (
    'yandex-search', 'wordstat', 'webmaster', 'metrika',
    'site', 'dzen', 'vk', 'pinterest'
));

ALTER TABLE keyword_queries
ADD COLUMN raw_response_id text
REFERENCES raw_tool_responses(id) ON DELETE RESTRICT;

ALTER TABLE serp_snapshots
ADD COLUMN raw_response_id text
REFERENCES raw_tool_responses(id) ON DELETE RESTRICT;

ALTER TABLE article_media
ADD COLUMN width integer CHECK (width IS NULL OR width > 0),
ADD COLUMN height integer CHECK (height IS NULL OR height > 0),
ADD CONSTRAINT article_media_dimensions_paired
CHECK ((width IS NULL) = (height IS NULL));
