import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, BarChart3, FileImage, FilePlus2, LayoutDashboard, LogOut, Save, Send, Trash2, Upload } from "lucide-react";

import { ARTICLE_CATEGORIES, slugifyArticleTitle } from "../lib/article-store";
import { adminApi, AdminApiError, type AdminUser, type ArticleInput, type ContentArticle } from "../lib/admin-api";

type AdminPageProps = { onNavigate: (path: string) => void };

function emptyArticle(): ArticleInput {
  return {
    title: "",
    slug: "",
    category: ARTICLE_CATEGORIES[0],
    excerpt: "",
    content: "",
    cover_media_id: null,
    body_media_ids: [],
    cover_image_url: null,
    cover_image_alt: "",
    seo_title: "",
    meta_description: "",
    focus_keyphrase: "",
    canonical_url: "",
    author_name: "Редакция VedicWay",
    status: "draft",
  };
}

function asInput(article: ContentArticle): ArticleInput {
  const {
    id: _id,
    revision: _revision,
    created_at: _created,
    updated_at: _updated,
    published_at: _published,
    coverImage: _cover,
    bodyMedia: _body,
    ...value
  } = article;
  return value;
}

export function AdminPage({ onNavigate }: AdminPageProps) {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [articles, setArticles] = useState<ContentArticle[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ArticleInput>(emptyArticle);
  const [savedDraft, setSavedDraft] = useState(() => JSON.stringify(emptyArticle()));
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<"overview" | "editor">("overview");
  const contentRef = useRef<HTMLTextAreaElement>(null);
  const dirty = JSON.stringify(draft) !== savedDraft;

  useEffect(() => {
    document.title = "Административная панель — VedicWay";
    adminApi.me().then(({ user: current }) => {
      setUser(current);
      return adminApi.articles();
    }).then(({ items }) => setArticles(items)).catch(() => {}).finally(() => setAuthLoading(false));
  }, []);

  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault();
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);

  const counts = useMemo(() => ({
    published: articles.filter((article) => article.status === "published").length,
    drafts: articles.filter((article) => article.status === "draft").length,
  }), [articles]);

  const reload = async () => {
    const { items } = await adminApi.articles();
    setArticles(items);
    return items;
  };

  const openArticle = (article: ContentArticle) => {
    if (dirty && !window.confirm("Открыть другой материал без сохранения изменений?")) return;
    const value = asInput(article);
    setActiveId(article.id);
    setDraft(value);
    setSavedDraft(JSON.stringify(value));
    setView("editor");
    setNotice("");
  };

  const newArticle = () => {
    if (dirty && !window.confirm("Создать новый материал без сохранения изменений?")) return;
    const value = emptyArticle();
    setActiveId(null);
    setDraft(value);
    setSavedDraft(JSON.stringify(value));
    setView("editor");
    setNotice("Новый черновик готов.");
  };

  const update = <K extends keyof ArticleInput>(key: K, value: ArticleInput[K]) => setDraft((current) => ({ ...current, [key]: value }));

  const persist = async (publish: boolean) => {
    setBusy(true);
    setNotice("");
    const value: ArticleInput = {
      ...draft,
      slug: draft.slug || slugifyArticleTitle(draft.title),
      seo_title: draft.seo_title || draft.title,
      status: publish ? "published" : draft.status,
    };
    try {
      const saved = activeId ? await adminApi.updateArticle(activeId, value) : await adminApi.createArticle(value);
      setActiveId(saved.id);
      setDraft(asInput(saved));
      setSavedDraft(JSON.stringify(asInput(saved)));
      await reload();
      setNotice(publish ? "Материал опубликован в гиде." : "Черновик сохранён в базе данных.");
    } catch (error) {
      setNotice(error instanceof AdminApiError ? error.message : "Не удалось сохранить материал.");
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file: File, cover: boolean) => {
    const alt = cover ? draft.cover_image_alt : window.prompt("Опишите изображение для читателей и поисковых систем:", "")?.trim() ?? "";
    if (!alt) {
      setNotice("Перед загрузкой добавьте содержательное описание изображения.");
      return;
    }
    setBusy(true);
    try {
      const { asset } = await adminApi.uploadMedia(file, cover ? "cover" : "body", alt);
      if (cover) {
        setDraft((current) => ({
          ...current,
          cover_media_id: asset.id,
          cover_image_url: asset.url,
          cover_image_alt: asset.alt,
        }));
      } else {
        const marker = `\n\n{{media:${asset.id}}}\n\n`;
        const textarea = contentRef.current;
        const start = textarea?.selectionStart ?? draft.content.length;
        const end = textarea?.selectionEnd ?? start;
        setDraft((current) => ({
          ...current,
          content: `${current.content.slice(0, start)}${marker}${current.content.slice(end)}`,
          body_media_ids: [...current.body_media_ids, asset.id],
        }));
      }
      setNotice(`Изображение подготовлено: ${asset.width}×${asset.height} WebP.`);
    } catch (error) {
      setNotice(error instanceof AdminApiError ? error.message : "Изображение не загрузилось.");
    } finally {
      setBusy(false);
    }
  };

  if (authLoading) return <div className="admin-loading">Проверяем защищённую сессию…</div>;
  if (!user) return <AdminLogin onSuccess={async (current) => { setUser(current); setArticles((await adminApi.articles()).items); }} onNavigate={onNavigate} />;

  return (
    <div className="admin-page">
      <aside className="admin-rail">
        <button className="admin-brand" type="button" onClick={() => onNavigate("/")}><img src="/assets/brand-mark.png" alt="" /><span>VedicWay<small>Управление сайтом</small></span></button>
        <nav aria-label="Разделы административной панели">
          <button className={view === "overview" ? "is-active" : ""} type="button" onClick={() => setView("overview")}><LayoutDashboard /> Обзор</button>
          <button className={view === "editor" ? "is-active" : ""} type="button" onClick={() => setView("editor")}><FileImage /> Материалы <span>{articles.length}</span></button>
        </nav>
        <div className="admin-rail__user"><strong>{user.name}</strong><span>{user.email}</span><button type="button" onClick={async () => { await adminApi.logout(); setUser(null); }}><LogOut /> Выйти</button></div>
      </aside>

      <main className="admin-main">
        {view === "overview" ? (
          <section className="admin-overview">
            <header><div><span>Административная панель</span><h1>Состояние редакции</h1><p>Материалы живут в серверной базе, а публикация доступна только роли admin.</p></div><button type="button" onClick={newArticle}><FilePlus2 /> Новый материал</button></header>
            <div className="admin-stats"><article><BarChart3 /><span>Опубликовано</span><strong>{counts.published}</strong></article><article><Save /><span>Черновики</span><strong>{counts.drafts}</strong></article><article><FileImage /><span>Всего материалов</span><strong>{articles.length}</strong></article></div>
            <section className="admin-recent"><header><h2>Последние материалы</h2><button type="button" onClick={() => setView("editor")}>Открыть редакцию</button></header>{articles.length ? articles.slice(0, 8).map((article) => <button type="button" key={article.id} onClick={() => openArticle(article)}><span><strong>{article.title}</strong><small>{article.category} · версия {article.revision}</small></span><em className={article.status}>{article.status === "published" ? "Опубликовано" : "Черновик"}</em></button>) : <p>Материалов пока нет. Создайте первый черновик.</p>}</section>
          </section>
        ) : (
          <section className="admin-editor">
            <header className="admin-editor__top"><div><button type="button" onClick={() => setView("overview")}><ArrowLeft /> Обзор</button><span>{dirty ? "Есть несохранённые изменения" : "Все изменения сохранены"}</span></div><div><button type="button" disabled={busy} onClick={() => persist(false)}><Save /> Сохранить</button><button className="is-primary" type="button" disabled={busy} onClick={() => persist(true)}><Send /> Опубликовать</button></div></header>
            <div className="admin-editor__layout">
              <aside className="admin-articles"><button className="admin-new" type="button" onClick={newArticle}><FilePlus2 /> Новая статья</button>{articles.map((article) => <button className={activeId === article.id ? "is-active" : ""} type="button" key={article.id} onClick={() => openArticle(article)}><strong>{article.title}</strong><small>{article.status === "published" ? "Опубликовано" : "Черновик"}</small></button>)}</aside>
              <div className="admin-form">
                <p className="admin-notice" role="status">{notice}</p>
                <section className="admin-card">
                  <label>Заголовок статьи<input value={draft.title} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value, slug: current.slug || slugifyArticleTitle(event.target.value) }))} /></label>
                  <div className="admin-fields"><label>Раздел<select value={draft.category} onChange={(event) => update("category", event.target.value)}>{ARTICLE_CATEGORIES.map((category) => <option key={category}>{category}</option>)}</select></label><label>Автор<input value={draft.author_name} onChange={(event) => update("author_name", event.target.value)} /></label></div>
                  <label>Лид <small>{draft.excerpt.length}/500</small><textarea rows={3} maxLength={500} value={draft.excerpt} onChange={(event) => update("excerpt", event.target.value)} /></label>
                </section>
                <section className="admin-card admin-cover"><header><div><h2>Обложка</h2><p>Единый формат карточек: 16:9, изображение обрезается только через object-fit.</p></div><label className="admin-upload"><Upload /> Загрузить<input type="file" accept="image/jpeg,image/png,image/webp,image/avif" onChange={(event) => event.target.files?.[0] && upload(event.target.files[0], true)} /></label></header><label>Описание обложки<input value={draft.cover_image_alt} onChange={(event) => update("cover_image_alt", event.target.value)} placeholder="Что изображено и почему это важно для статьи" /></label><div className="admin-cover__preview">{draft.cover_image_url ? <img src={draft.cover_image_url} alt={draft.cover_image_alt} /> : <span><FileImage /> Обложка появится здесь</span>}</div></section>
                <section className="admin-card"><header className="admin-content-header"><div><h2>Текст статьи</h2><p>Подзаголовок: ## Текст. Изображение вставляется в позицию курсора.</p></div><label className="admin-upload"><FileImage /> Добавить изображение<input type="file" accept="image/jpeg,image/png,image/webp,image/avif" onChange={(event) => event.target.files?.[0] && upload(event.target.files[0], false)} /></label></header><textarea ref={contentRef} className="admin-content" rows={22} value={draft.content} onChange={(event) => update("content", event.target.value)} /></section>
                <section className="admin-card"><h2>Поисковое представление</h2><label>Адрес<div className="admin-slug"><span>/guide/</span><input value={draft.slug} onChange={(event) => update("slug", slugifyArticleTitle(event.target.value))} /></div></label><label>SEO-заголовок <small>{draft.seo_title.length}/180</small><input value={draft.seo_title} onChange={(event) => update("seo_title", event.target.value)} /></label><label>Метаописание <small>{draft.meta_description.length}/320</small><textarea rows={3} value={draft.meta_description} onChange={(event) => update("meta_description", event.target.value)} /></label><div className="admin-fields"><label>Основной запрос<input value={draft.focus_keyphrase} onChange={(event) => update("focus_keyphrase", event.target.value)} /></label><label>Канонический URL<input type="url" value={draft.canonical_url} onChange={(event) => update("canonical_url", event.target.value)} /></label></div></section>
                {activeId && <button className="admin-delete" type="button" onClick={async () => { if (!window.confirm("Удалить материал без возможности восстановления?")) return; await adminApi.deleteArticle(activeId); await reload(); newArticle(); }}><Trash2 /> Удалить материал</button>}
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

function AdminLogin({ onSuccess, onNavigate }: { onSuccess: (user: AdminUser) => void; onNavigate: (path: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <main className="admin-login"><button type="button" onClick={() => onNavigate("/")}><ArrowLeft /> На сайт</button><form onSubmit={async (event) => { event.preventDefault(); setBusy(true); setError(""); try { onSuccess((await adminApi.login(email, password)).user); } catch (caught) { setError(caught instanceof AdminApiError ? caught.message : "Вход не выполнен"); } finally { setBusy(false); } }}><img src="/assets/brand-mark.png" alt="" /><span>Закрытый раздел</span><h1>Вход в редакцию</h1><p>Публикация и настройки доступны только администраторам.</p><label>Рабочая почта<input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} /></label><label>Пароль<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>{error && <p className="admin-login__error" role="alert">{error}</p>}<button className="admin-login__submit" type="submit" disabled={busy}>{busy ? "Проверяем…" : "Войти"}</button></form></main>;
}
