export type ContentSection = "guide" | "blog";
export type ArticleDifficulty = "beginner" | "expert";

export type ContentMediaAsset = {
  id: string;
  provider: "remote";
  storageKey: string;
  url: string;
  sources: Array<{ url: string; width: number; mimeType: string }>;
  width: number;
  height: number;
  mimeType: string;
  sizeBytes: number;
  alt: string;
  title: string;
  caption: string;
  createdAt: string;
};

export type ContentArticleSummary = {
  id: string;
  section: ContentSection;
  difficulty: ArticleDifficulty;
  difficulty_label: "Новичок" | "Эксперт";
  title: string;
  slug: string;
  category: string;
  excerpt: string;
  cover_image_url: string | null;
  cover_image_alt: string;
  canonical_url: string;
  author_name: string;
  tags: string[];
  updated_at: string;
  published_at: string | null;
  coverImage: ContentMediaAsset | null;
};

export type ContentArticle = ContentArticleSummary & {
  content_html: string;
  content_sections: [string, string] | string[];
  content_format: "html.v1";
  body_media_ids: string[];
  seo_title: string;
  meta_description: string;
  focus_keyphrase: string;
  schema_extra: Record<string, unknown>;
  status: "published";
  revision: number;
  created_at: string;
  word_count: number;
  reading_minutes: number;
  comment_count: number;
  cover_media_id: string | null;
  bodyMedia: ContentMediaAsset[];
  related: ContentArticleSummary[];
};

export type ContentComment = {
  id: string;
  display_name: string;
  body: string;
  created_at: string;
};

export class ContentApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
  }
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      error?: { message?: string; code?: string };
    };
    throw new ContentApiError(
      response.status,
      payload.error?.message ?? "Запрос не выполнен",
      payload.error?.code,
    );
  }
  return response.json() as Promise<T>;
}

export function publicArticles(section: ContentSection) {
  return api<{ items: ContentArticleSummary[]; total: number }>(
    `/api/v1/content/${section}/articles`,
  );
}

export function publicArticle(section: ContentSection, slug: string) {
  return api<ContentArticle>(
    `/api/v1/content/${section}/articles/${encodeURIComponent(slug)}`,
  );
}

export function publicComments(section: ContentSection, slug: string) {
  return api<{ items: ContentComment[] }>(
    `/api/v1/content/${section}/articles/${encodeURIComponent(slug)}/comments`,
  );
}

export function addPublicComment(
  section: ContentSection,
  slug: string,
  payload: { display_name: string; body: string; website: string },
) {
  return api<ContentComment>(
    `/api/v1/content/${section}/articles/${encodeURIComponent(slug)}/comments`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}
