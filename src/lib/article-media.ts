import type { ArticleMediaAsset, ArticleMediaSource } from "./article-store";

export const ARTICLE_MEDIA_UPLOAD_ENDPOINT = "/api/v1/admin/media";
export const ARTICLE_MEDIA_ACCEPT = "image/jpeg,image/png,image/webp,image/avif";
export const ARTICLE_MEDIA_MAX_BYTES = 12 * 1024 * 1024;

const ALLOWED_MEDIA_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/avif"]);
const DEV_MEDIA_DATABASE = "vedicway-dev-article-media";
const DEV_MEDIA_STORE = "assets";

export type ArticleMediaPurpose = "cover" | "body";

export type ArticleMediaUpload = {
  file: File;
  purpose: ArticleMediaPurpose;
  alt: string;
  title?: string;
  caption?: string;
};

type RemoteMediaPayload = {
  asset?: Partial<ArticleMediaAsset>;
} & Partial<ArticleMediaAsset>;

function mediaId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `media-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function safeArticleMediaUrl(value: unknown) {
  if (typeof value !== "string") return "";
  if ((value.startsWith("/") && !value.startsWith("//")) || value.startsWith("https://")) return value;
  if (import.meta.env.DEV && value.startsWith("http://")) return value;
  return "";
}

function normalizeSources(value: unknown): ArticleMediaSource[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((source) => {
    if (!source || typeof source !== "object") return [];
    const candidate = source as Partial<ArticleMediaSource>;
    const url = safeArticleMediaUrl(candidate.url);
    if (!url || typeof candidate.width !== "number" || typeof candidate.mimeType !== "string") return [];
    return [{ url, width: candidate.width, mimeType: candidate.mimeType }];
  }).sort((left, right) => left.width - right.width);
}

export function validateArticleMediaFile(file: File) {
  if (!ALLOWED_MEDIA_TYPES.has(file.type)) {
    throw new Error("Поддерживаются JPEG, PNG, WebP и AVIF.");
  }
  if (file.size <= 0 || file.size > ARTICLE_MEDIA_MAX_BYTES) {
    throw new Error("Размер изображения должен быть не больше 12 МБ.");
  }
}

async function imageDimensions(file: File) {
  if (typeof createImageBitmap !== "function") return { width: 0, height: 0 };
  const bitmap = await createImageBitmap(file);
  try {
    return { width: bitmap.width, height: bitmap.height };
  } finally {
    bitmap.close();
  }
}

function openDevMediaDatabase() {
  if (typeof indexedDB === "undefined") throw new Error("Локальное хранилище изображений недоступно.");
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DEV_MEDIA_DATABASE, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(DEV_MEDIA_STORE)) {
        request.result.createObjectStore(DEV_MEDIA_STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Не удалось открыть локальное медиахранилище."));
  });
}

async function writeDevMedia(key: string, file: File) {
  const database = await openDevMediaDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(DEV_MEDIA_STORE, "readwrite");
      transaction.objectStore(DEV_MEDIA_STORE).put(file, key);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("Не удалось сохранить изображение."));
    });
  } finally {
    database.close();
  }
}

async function readDevMedia(key: string) {
  const database = await openDevMediaDatabase();
  try {
    return await new Promise<Blob | null>((resolve, reject) => {
      const request = database.transaction(DEV_MEDIA_STORE, "readonly").objectStore(DEV_MEDIA_STORE).get(key);
      request.onsuccess = () => resolve(request.result instanceof Blob ? request.result : null);
      request.onerror = () => reject(request.error ?? new Error("Не удалось прочитать изображение."));
    });
  } finally {
    database.close();
  }
}

async function uploadRemote(input: ArticleMediaUpload, fetcher: typeof fetch): Promise<ArticleMediaAsset> {
  const form = new FormData();
  form.set("file", input.file);
  form.set("purpose", input.purpose);
  form.set("alt", input.alt.trim());
  form.set("title", input.title?.trim() ?? "");
  form.set("caption", input.caption?.trim() ?? "");
  const response = await fetcher(ARTICLE_MEDIA_UPLOAD_ENDPOINT, {
    method: "POST",
    credentials: "same-origin",
    body: form,
  });
  if (!response.ok) {
    const error = new Error(response.status === 401 || response.status === 403
      ? "Для загрузки изображения нужна активная сессия редактора."
      : "Не удалось загрузить изображение в медиахранилище.");
    Object.assign(error, { status: response.status });
    throw error;
  }
  const payload = await response.json() as RemoteMediaPayload;
  const candidate = payload.asset ?? payload;
  const url = safeArticleMediaUrl(candidate.url);
  if (!candidate.id || !candidate.storageKey || !url || !candidate.mimeType) {
    throw new Error("Медиасервис вернул неполный ответ.");
  }
  return {
    id: candidate.id,
    provider: "remote",
    storageKey: candidate.storageKey,
    url,
    sources: normalizeSources(candidate.sources),
    width: Number(candidate.width) || 0,
    height: Number(candidate.height) || 0,
    mimeType: candidate.mimeType,
    sizeBytes: Number(candidate.sizeBytes) || input.file.size,
    alt: candidate.alt?.trim() || input.alt.trim(),
    title: candidate.title?.trim() || input.title?.trim() || "",
    caption: candidate.caption?.trim() || input.caption?.trim() || "",
    createdAt: candidate.createdAt || new Date().toISOString(),
  };
}

async function uploadDevelopmentFallback(input: ArticleMediaUpload): Promise<ArticleMediaAsset> {
  const id = mediaId();
  const storageKey = `article-media/${id}`;
  const dimensions = await imageDimensions(input.file);
  await writeDevMedia(storageKey, input.file);
  return {
    id,
    provider: "dev-indexeddb",
    storageKey,
    url: "",
    sources: [],
    ...dimensions,
    mimeType: input.file.type,
    sizeBytes: input.file.size,
    alt: input.alt.trim(),
    title: input.title?.trim() ?? "",
    caption: input.caption?.trim() ?? "",
    createdAt: new Date().toISOString(),
  };
}

export async function uploadArticleMedia(input: ArticleMediaUpload, fetcher: typeof fetch = fetch) {
  validateArticleMediaFile(input.file);
  if (!input.alt.trim()) throw new Error("Добавьте альтернативное описание изображения.");
  try {
    return await uploadRemote(input, fetcher);
  } catch (reason) {
    const status = typeof reason === "object" && reason !== null && "status" in reason ? Number(reason.status) : 0;
    if (!import.meta.env.DEV || (status !== 0 && status !== 404 && status < 500)) throw reason;
    return uploadDevelopmentFallback(input);
  }
}

export async function resolveArticleMediaUrl(asset: ArticleMediaAsset) {
  const remote = safeArticleMediaUrl(asset.url);
  if (remote) return { url: remote, revoke: false };
  if (asset.provider !== "dev-indexeddb") return { url: "", revoke: false };
  const blob = await readDevMedia(asset.storageKey);
  if (!blob) return { url: "", revoke: false };
  return { url: URL.createObjectURL(blob), revoke: true };
}

export function formatMediaBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} КБ`;
  return `${(value / 1024 / 1024).toFixed(1).replace(".", ",")} МБ`;
}
