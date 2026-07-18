export type AdminUser = { id: string; email: string; name: string; role: "admin" };

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

export type ContentArticle = {
  id: string;
  title: string;
  slug: string;
  category: string;
  excerpt: string;
  content: string;
  cover_media_id: string | null;
  body_media_ids: string[];
  cover_image_url: string | null;
  cover_image_alt: string;
  seo_title: string;
  meta_description: string;
  focus_keyphrase: string;
  canonical_url: string;
  author_name: string;
  status: "draft" | "published";
  revision: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  coverImage: ContentMediaAsset | null;
  bodyMedia: ContentMediaAsset[];
};

export type ArticleInput = Omit<ContentArticle, "id" | "revision" | "created_at" | "updated_at" | "published_at" | "coverImage" | "bodyMedia">;

export class AdminApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

function csrfToken() {
  const names = ["__Host-vedicway-csrf", "vw_admin_csrf"];
  for (const part of document.cookie.split(";")) {
    const [name, ...value] = part.trim().split("=");
    if (names.includes(name)) return decodeURIComponent(value.join("="));
  }
  return "";
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const mutating = init.method && !["GET", "HEAD"].includes(init.method.toUpperCase());
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body instanceof FormData ? {} : init.body ? { "Content-Type": "application/json" } : {}),
      ...(mutating && !path.endsWith("/auth/login") ? { "X-CSRF-Token": csrfToken() } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { error?: { message?: string; code?: string } };
    throw new AdminApiError(response.status, payload.error?.message ?? "Запрос не выполнен", payload.error?.code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const adminApi = {
  me: () => api<{ user: AdminUser }>("/api/v1/admin/me"),
  login: (email: string, password: string) => api<{ user: AdminUser }>("/api/v1/admin/auth/login", {
    method: "POST",
    headers: { "X-Admin-Request": "1" },
    body: JSON.stringify({ email, password }),
  }),
  logout: () => api<void>("/api/v1/admin/auth/logout", { method: "POST" }),
  articles: () => api<{ items: ContentArticle[] }>("/api/v1/admin/articles"),
  createArticle: (value: ArticleInput) => api<ContentArticle>("/api/v1/admin/articles", { method: "POST", body: JSON.stringify(value) }),
  updateArticle: (id: string, value: ArticleInput) => api<ContentArticle>(`/api/v1/admin/articles/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(value) }),
  deleteArticle: (id: string) => api<void>(`/api/v1/admin/articles/${encodeURIComponent(id)}`, { method: "DELETE" }),
  uploadMedia: (file: File, purpose: "cover" | "body", alt: string, title = "", caption = "") => {
    const body = new FormData();
    body.append("file", file);
    body.append("purpose", purpose);
    body.append("alt", alt);
    body.append("title", title);
    body.append("caption", caption);
    return api<{ asset: ContentMediaAsset }>("/api/v1/admin/media", { method: "POST", body });
  },
  deleteMedia: (id: string) => api<void>(`/api/v1/admin/media/${encodeURIComponent(id)}`, { method: "DELETE" }),
};

export async function publicArticles() {
  return api<{ items: ContentArticle[] }>("/api/v1/content/articles");
}

export async function publicArticle(slug: string) {
  return api<ContentArticle>(`/api/v1/content/articles/${encodeURIComponent(slug)}`);
}
