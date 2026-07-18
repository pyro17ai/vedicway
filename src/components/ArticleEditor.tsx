import { type ChangeEvent, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, ExternalLink, FilePlus2, ImagePlus, Save, Send, Trash2, X } from "lucide-react";

import { ARTICLE_MEDIA_ACCEPT, formatMediaBytes, uploadArticleMedia } from "../lib/article-media";
import {
  ARTICLE_CATEGORIES,
  articleMediaToken,
  createArticleDraft,
  mediaIdFromArticleBlock,
  readArticles,
  removeArticle,
  uniqueArticleSlug,
  writeArticle,
  type ArticleMediaAsset,
  type GuideArticle,
} from "../lib/article-store";
import { ArticleMedia } from "./ArticleMedia";

type ArticleEditorProps = {
  onNavigate: (path: string) => void;
};

type ValidationErrors = Partial<Record<"title" | "slug" | "excerpt" | "content" | "coverImage" | "metaDescription", string>>;

function snapshot(article: GuideArticle) {
  return JSON.stringify(article);
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function replaceMedia(article: GuideArticle, mediaId: string, patch: Partial<ArticleMediaAsset>) {
  return {
    ...article,
    coverImage: article.coverImage?.id === mediaId ? { ...article.coverImage, ...patch } : article.coverImage,
    bodyMedia: article.bodyMedia.map((asset) => asset.id === mediaId ? { ...asset, ...patch } : asset),
  };
}

function EditorMediaFields({ asset, onChange }: { asset: ArticleMediaAsset; onChange: (patch: Partial<ArticleMediaAsset>) => void }) {
  return (
    <div className="editor-media-fields">
      <div className="editor-field"><label htmlFor={`media-alt-${asset.id}`}>Альтернативное описание</label><input id={`media-alt-${asset.id}`} value={asset.alt} onChange={(event) => onChange({ alt: event.target.value })} placeholder="Что изображено и зачем это важно" /></div>
      <div className="editor-field-row">
        <div className="editor-field"><label htmlFor={`media-title-${asset.id}`}>Заголовок изображения</label><input id={`media-title-${asset.id}`} value={asset.title} onChange={(event) => onChange({ title: event.target.value })} /></div>
        <div className="editor-field"><label htmlFor={`media-caption-${asset.id}`}>Подпись под изображением</label><input id={`media-caption-${asset.id}`} value={asset.caption} onChange={(event) => onChange({ caption: event.target.value })} /></div>
      </div>
    </div>
  );
}

export function ArticleEditor({ onNavigate }: ArticleEditorProps) {
  const [initialArticle] = useState<GuideArticle>(() => readArticles()[0] ?? createArticleDraft());
  const [articles, setArticles] = useState<GuideArticle[]>(() => readArticles());
  const [draft, setDraft] = useState<GuideArticle>(initialArticle);
  const [savedSnapshot, setSavedSnapshot] = useState(() => snapshot(initialArticle));
  const [errors, setErrors] = useState<ValidationErrors>({});
  const [notice, setNotice] = useState("Изменения сохраняются локально в этом браузере.");
  const [preview, setPreview] = useState(true);
  const [slugTouched, setSlugTouched] = useState(Boolean(initialArticle.slug));
  const [uploading, setUploading] = useState<"cover" | "body" | null>(null);

  const isDirty = snapshot(draft) !== savedSnapshot;
  const wordCount = useMemo(() => draft.content.trim().split(/\s+/).filter(Boolean).length, [draft.content]);

  useEffect(() => {
    document.title = "Редактор гида — VedicWay";
  }, []);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!isDirty) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [isDirty]);

  const update = <Key extends keyof GuideArticle>(key: Key, value: GuideArticle[Key]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  };

  const uploadMedia = async (purpose: "cover" | "body", event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(purpose);
    setNotice("Загружаем изображение и проверяем формат.");
    try {
      const fallbackAlt = draft.title.trim() || file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
      const asset = await uploadArticleMedia({ file, purpose, alt: fallbackAlt });
      setDraft((current) => purpose === "cover"
        ? { ...current, coverImage: asset }
        : { ...current, bodyMedia: [...current.bodyMedia, asset] });
      setErrors((current) => ({ ...current, coverImage: undefined }));
      setNotice(asset.provider === "dev-indexeddb"
        ? "Изображение сохранено в локальном dev-медиахранилище. В production оно будет загружено через защищённый media API."
        : "Изображение загружено в медиахранилище.");
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "Не удалось загрузить изображение.");
    } finally {
      setUploading(null);
    }
  };

  const insertBodyMedia = (asset: ArticleMediaAsset) => {
    const token = articleMediaToken(asset.id);
    if (draft.content.includes(token)) {
      setNotice("Это изображение уже вставлено в текст.");
      return;
    }
    update("content", `${draft.content.trimEnd()}${draft.content.trim() ? "\n\n" : ""}${token}\n\n`);
    setNotice("Изображение вставлено в конец текста. Переместите маркер целиком между нужными абзацами.");
  };

  const removeBodyMedia = (asset: ArticleMediaAsset) => {
    const token = articleMediaToken(asset.id);
    setDraft((current) => ({
      ...current,
      content: current.content.replaceAll(token, "").replace(/\n{3,}/g, "\n\n").trim(),
      bodyMedia: current.bodyMedia.filter((item) => item.id !== asset.id),
    }));
  };

  const startNew = () => {
    if (isDirty && !window.confirm("Есть несохранённые изменения. Создать новый черновик?")) return;
    const next = createArticleDraft();
    setDraft(next);
    setSavedSnapshot(snapshot(next));
    setErrors({});
    setNotice("Новый черновик готов к работе.");
    setSlugTouched(false);
  };

  const selectArticle = (article: GuideArticle) => {
    if (isDirty && !window.confirm("Перейти к другой статье без сохранения изменений?")) return;
    setDraft(article);
    setSavedSnapshot(snapshot(article));
    setErrors({});
    setNotice(article.status === "published" ? "Открыта опубликованная статья." : "Открыт черновик.");
    setSlugTouched(Boolean(article.slug));
  };

  const validate = (publish: boolean) => {
    const next: ValidationErrors = {};
    if (!draft.title.trim()) next.title = "Укажите заголовок";
    if (publish && !draft.excerpt.trim()) next.excerpt = "Для публикации нужен лид";
    if (publish && draft.content.trim().length < 120) next.content = "Для публикации нужно не меньше 120 знаков";
    if (publish && !draft.coverImage) next.coverImage = "Для публикации нужна обложка";
    if (publish && draft.coverImage && !draft.coverImage.alt.trim()) next.coverImage = "Добавьте описание обложки";
    if (publish && draft.bodyMedia.some((asset) => !asset.alt.trim())) next.content = "У каждого изображения в тексте должно быть альтернативное описание";
    if (publish && draft.metaDescription.trim().length < 70) next.metaDescription = "Метаописание должно содержать не меньше 70 знаков";
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const persist = (publish: boolean) => {
    if (!validate(publish)) {
      setNotice("Заполните отмеченные поля.");
      return;
    }
    const now = new Date().toISOString();
    const slug = uniqueArticleSlug(draft.slug || draft.title, draft.id, articles);
    const next: GuideArticle = {
      ...draft,
      title: draft.title.trim(),
      slug,
      excerpt: draft.excerpt.trim(),
      seoTitle: (draft.seoTitle || draft.title).trim(),
      status: publish ? "published" : draft.status,
      updatedAt: now,
      publishedAt: publish ? (draft.publishedAt ?? now) : draft.publishedAt,
    };
    const list = writeArticle(next);
    setArticles(list);
    setDraft(next);
    setSavedSnapshot(snapshot(next));
    setNotice(publish ? "Статья опубликована и появилась в гиде." : "Черновик сохранён.");
  };

  const deleteCurrent = () => {
    if (!articles.some((article) => article.id === draft.id)) return;
    if (!window.confirm("Удалить эту статью без возможности восстановления?")) return;
    const list = removeArticle(draft.id);
    const next = list[0] ?? createArticleDraft();
    setArticles(list);
    setDraft(next);
    setSavedSnapshot(snapshot(next));
    setNotice("Статья удалена.");
  };

  return (
    <div className="editor-page">
      <header className="editor-topbar">
        <div>
          <button type="button" onClick={() => onNavigate("/guide")}><ArrowLeft aria-hidden="true" /> Гид</button>
          <span>Редактор материалов</span>
          <small className={isDirty ? "is-dirty" : ""}>{isDirty ? "Есть несохранённые изменения" : "Все изменения сохранены"}</small>
        </div>
        <div>
          <button className="editor-secondary" type="button" onClick={() => setPreview((value) => !value)}>{preview ? "Скрыть предпросмотр" : "Показать предпросмотр"}</button>
          <button className="editor-secondary" type="button" onClick={() => persist(false)}><Save aria-hidden="true" /> Сохранить</button>
          <button className="editor-primary" type="button" onClick={() => persist(true)}><Send aria-hidden="true" /> Опубликовать</button>
        </div>
      </header>

      <main className={`editor-layout${preview ? " has-preview" : ""}`}>
        <aside className="editor-sidebar" aria-label="Материалы">
          <button className="editor-new" type="button" onClick={startNew}><FilePlus2 aria-hidden="true" /> Новая статья</button>
          <div className="editor-sidebar__heading"><span>Материалы</span><small>{articles.length}</small></div>
          <div className="editor-article-list">
            {articles.length === 0 && <p>Сохранённых материалов пока нет.</p>}
            {articles.map((article) => (
              <button className={article.id === draft.id ? "is-active" : ""} type="button" key={article.id} onClick={() => selectArticle(article)}>
                <span>{article.title || "Без названия"}</span>
                <small>{article.status === "published" ? "Опубликовано" : "Черновик"} · {formatShortDate(article.updatedAt)}</small>
              </button>
            ))}
          </div>
        </aside>

        <section className="editor-form" aria-label="Поля статьи">
          <header className="editor-form__header">
            <div><span>{draft.status === "published" ? "Опубликовано" : "Черновик"}</span><p role="status">{notice}</p></div>
            <button type="button" onClick={deleteCurrent} disabled={!articles.some((article) => article.id === draft.id)}><Trash2 aria-hidden="true" /> Удалить</button>
          </header>

          <section className="editor-card">
            <div className="editor-field editor-field--title">
              <label htmlFor="article-title">Заголовок статьи</label>
              <input id="article-title" value={draft.title} onChange={(event) => {
                const title = event.target.value;
                setDraft((current) => ({ ...current, title, slug: slugTouched ? current.slug : uniqueArticleSlug(title, current.id, articles) }));
                setErrors((current) => ({ ...current, title: undefined }));
              }} placeholder="Например: Как читать дома натальной карты" aria-invalid={Boolean(errors.title)} />
              {errors.title && <small className="editor-error">{errors.title}</small>}
            </div>
            <div className="editor-field-row">
              <div className="editor-field"><label htmlFor="article-category">Раздел</label><select id="article-category" value={draft.category} onChange={(event) => update("category", event.target.value)}>{ARTICLE_CATEGORIES.map((category) => <option key={category}>{category}</option>)}</select></div>
              <div className="editor-field"><label htmlFor="article-author">Автор</label><input id="article-author" value={draft.author} onChange={(event) => update("author", event.target.value)} /></div>
            </div>
            <div className="editor-field">
              <label htmlFor="article-excerpt">Лид <span>{draft.excerpt.length}/240</span></label>
              <textarea id="article-excerpt" rows={3} maxLength={240} value={draft.excerpt} onChange={(event) => update("excerpt", event.target.value)} placeholder="Два предложения, которые объясняют пользу материала." aria-invalid={Boolean(errors.excerpt)} />
              {errors.excerpt && <small className="editor-error">{errors.excerpt}</small>}
            </div>
            <section className="editor-media-section" aria-labelledby="cover-heading">
              <header>
                <div><span>Обложка</span><h2 id="cover-heading">Изображение карточки и статьи</h2></div>
                <label className="editor-media-upload">
                  <ImagePlus aria-hidden="true" /> {uploading === "cover" ? "Загружаем…" : draft.coverImage ? "Заменить" : "Добавить обложку"}
                  <input type="file" accept={ARTICLE_MEDIA_ACCEPT} disabled={uploading !== null} onChange={(event) => void uploadMedia("cover", event)} />
                </label>
              </header>
              {draft.coverImage ? (
                <div className="editor-cover-media">
                  <div className="editor-cover-media__preview">
                    <ArticleMedia asset={draft.coverImage} sizes="460px" />
                    <button type="button" aria-label="Удалить обложку" onClick={() => update("coverImage", null)}><X aria-hidden="true" /></button>
                    <small>{draft.coverImage.mimeType.replace("image/", "").toUpperCase()} · {formatMediaBytes(draft.coverImage.sizeBytes)}{draft.coverImage.width ? ` · ${draft.coverImage.width}×${draft.coverImage.height}` : ""}</small>
                  </div>
                  <EditorMediaFields asset={draft.coverImage} onChange={(patch) => setDraft((current) => replaceMedia(current, draft.coverImage!.id, patch))} />
                </div>
              ) : (
                <p className="editor-media-hint">Горизонтальная обложка показывается в едином формате 16:9. Сервис аккуратно обрежет края без растяжения; рекомендуемый исходник от 1600×900 px.</p>
              )}
              {errors.coverImage && <small className="editor-error">{errors.coverImage}</small>}
            </section>
            <div className="editor-field">
              <label htmlFor="article-content">Текст статьи <span>{wordCount} слов</span></label>
              <textarea className="editor-content" id="article-content" rows={18} value={draft.content} onChange={(event) => update("content", event.target.value)} placeholder={"Используйте пустую строку между абзацами.\n\n## Подзаголовок\n\nОсновной текст."} aria-invalid={Boolean(errors.content)} />
              {errors.content && <small className="editor-error">{errors.content}</small>}
            </div>
            <section className="editor-media-section" aria-labelledby="body-media-heading">
              <header>
                <div><span>Медиатека статьи</span><h2 id="body-media-heading">Изображения внутри материала</h2></div>
                <label className="editor-media-upload">
                  <ImagePlus aria-hidden="true" /> {uploading === "body" ? "Загружаем…" : "Добавить изображение"}
                  <input type="file" accept={ARTICLE_MEDIA_ACCEPT} disabled={uploading !== null} onChange={(event) => void uploadMedia("body", event)} />
                </label>
              </header>
              {draft.bodyMedia.length === 0 ? <p className="editor-media-hint">Добавьте изображение, заполните описание и вставьте его между абзацами. В тексте появится короткий маркер вида <code>{"{{media:…}}"}</code>.</p> : (
                <div className="editor-body-media-list">
                  {draft.bodyMedia.map((asset) => {
                    const inserted = draft.content.split(/\n{2,}/).some((block) => mediaIdFromArticleBlock(block) === asset.id);
                    return (
                      <article key={asset.id}>
                        <ArticleMedia asset={asset} sizes="180px" />
                        <div>
                          <EditorMediaFields asset={asset} onChange={(patch) => setDraft((current) => replaceMedia(current, asset.id, patch))} />
                          <footer><button type="button" onClick={() => insertBodyMedia(asset)} disabled={inserted}>{inserted ? "Вставлено в текст" : "Вставить в текст"}</button><button type="button" onClick={() => removeBodyMedia(asset)}>Удалить</button></footer>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </section>
          </section>

          <section className="editor-card editor-seo">
            <header><div><span>Поисковое представление</span><h2>SEO и адрес материала</h2></div><Check aria-hidden="true" /></header>
            <div className="editor-field"><label htmlFor="article-slug">Адрес</label><div className="editor-slug"><span>/guide/</span><input id="article-slug" value={draft.slug} onChange={(event) => { setSlugTouched(true); update("slug", uniqueArticleSlug(event.target.value, draft.id, articles)); }} placeholder="adres-stati" /></div></div>
            <div className="editor-field"><label htmlFor="article-seo-title">Заголовок в поиске <span>{draft.seoTitle.length}/60</span></label><input id="article-seo-title" maxLength={70} value={draft.seoTitle} onChange={(event) => update("seoTitle", event.target.value)} placeholder={draft.title || "Заголовок статьи"} /></div>
            <div className="editor-field"><label htmlFor="article-meta">Метаописание <span>{draft.metaDescription.length}/160</span></label><textarea id="article-meta" rows={3} maxLength={180} value={draft.metaDescription} onChange={(event) => update("metaDescription", event.target.value)} aria-invalid={Boolean(errors.metaDescription)} />{errors.metaDescription && <small className="editor-error">{errors.metaDescription}</small>}</div>
            <div className="editor-field-row">
              <div className="editor-field"><label htmlFor="article-keyphrase">Основной запрос</label><input id="article-keyphrase" value={draft.focusKeyphrase} onChange={(event) => update("focusKeyphrase", event.target.value)} /></div>
              <div className="editor-field"><label htmlFor="article-canonical">Канонический URL</label><input id="article-canonical" type="url" value={draft.canonicalUrl} onChange={(event) => update("canonicalUrl", event.target.value)} placeholder="https://vedicway.ru/guide/..." /></div>
            </div>
          </section>
        </section>

        {preview && (
          <aside className="editor-preview" aria-label="Предпросмотр статьи">
            <header><span>Предпросмотр</span>{draft.status === "published" && draft.slug && <button type="button" onClick={() => onNavigate(`/guide/${draft.slug}`)}><ExternalLink aria-hidden="true" /> Открыть</button>}</header>
            <article>
              {draft.coverImage && <ArticleMedia asset={draft.coverImage} className="editor-preview__cover" sizes="390px" loading="eager" />}
              <span>{draft.category}</span>
              <h1>{draft.title || "Заголовок статьи"}</h1>
              <p className="editor-preview__lead">{draft.excerpt || "Здесь появится лид материала."}</p>
              <div>{draft.content ? draft.content.split(/\n{2,}/).slice(0, 10).map((block, index) => {
                const mediaId = mediaIdFromArticleBlock(block);
                const asset = mediaId ? draft.bodyMedia.find((item) => item.id === mediaId) : null;
                if (asset) return <figure className="editor-preview__media" key={asset.id}><ArticleMedia asset={asset} sizes="390px" />{asset.caption && <figcaption>{asset.caption}</figcaption>}</figure>;
                return block.startsWith("## ") ? <h2 key={index}>{block.slice(3)}</h2> : <p key={index}>{block}</p>;
              }) : <p>Начните писать текст, чтобы увидеть структуру страницы.</p>}</div>
            </article>
          </aside>
        )}
      </main>
    </div>
  );
}
