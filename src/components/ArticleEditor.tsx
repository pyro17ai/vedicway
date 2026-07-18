import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, ExternalLink, FilePlus2, Save, Send, Trash2 } from "lucide-react";

import {
  ARTICLE_CATEGORIES,
  createArticleDraft,
  readArticles,
  removeArticle,
  uniqueArticleSlug,
  writeArticle,
  type GuideArticle,
} from "../lib/article-store";

type ArticleEditorProps = {
  onNavigate: (path: string) => void;
};

type ValidationErrors = Partial<Record<"title" | "slug" | "excerpt" | "content" | "metaDescription", string>>;

function snapshot(article: GuideArticle) {
  return JSON.stringify(article);
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
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
            <div className="editor-field">
              <label htmlFor="article-content">Текст статьи <span>{wordCount} слов</span></label>
              <textarea className="editor-content" id="article-content" rows={18} value={draft.content} onChange={(event) => update("content", event.target.value)} placeholder={"Используйте пустую строку между абзацами.\n\n## Подзаголовок\n\nОсновной текст."} aria-invalid={Boolean(errors.content)} />
              {errors.content && <small className="editor-error">{errors.content}</small>}
            </div>
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
              <span>{draft.category}</span>
              <h1>{draft.title || "Заголовок статьи"}</h1>
              <p className="editor-preview__lead">{draft.excerpt || "Здесь появится лид материала."}</p>
              <div>{draft.content ? draft.content.split(/\n{2,}/).slice(0, 8).map((block, index) => block.startsWith("## ") ? <h2 key={index}>{block.slice(3)}</h2> : <p key={index}>{block}</p>) : <p>Начните писать текст, чтобы увидеть структуру страницы.</p>}</div>
            </article>
          </aside>
        )}
      </main>
    </div>
  );
}
