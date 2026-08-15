import { lazy, Suspense, useEffect, useState } from "react";

import { AstrologyWheel } from "./components/AstrologyWheel";
import { ArticlePage } from "./components/ArticlePage";
import { BirthChartForm } from "./components/BirthChartForm";
import { BlogPage } from "./components/BlogPage";
import { FaqSection, faqItems } from "./components/FaqSection";
import { GuidePage } from "./components/GuidePage";
import { LegalPage, type LegalDocumentKind } from "./components/LegalPage";
import { NotFoundPage } from "./components/NotFoundPage";
import { ResultsShowcase } from "./components/ResultsShowcase";
import { RecoveryPage } from "./components/RecoveryPage";
import { RectificationFlow } from "./components/RectificationFlow";
import { SiteHeader } from "./components/SiteHeader";
import { TrustPage, type TrustPageKind } from "./components/TrustPage";
import { trackPageView } from "./lib/analytics";
import { applySeo, publicOrigin } from "./lib/seo";
import type { SeoBootstrap } from "./lib/seo-bootstrap";

const ChartWorkspace = lazy(() =>
  import("./components/ChartWorkspace").then((module) => ({
    default: module.ChartWorkspace,
  })),
);

type LandingScreenProps = {
  onChartCreated: (chartId: string) => void;
  onNavigate: (path: string) => void;
  initialFormMode?: "calculate" | "recovery";
};

type ChartScreenProps = {
  chartId: string;
  onNavigate: (path: string) => void;
};

function ChartScreen({ chartId, onNavigate }: ChartScreenProps) {
  useEffect(() => applySeo({
    title: "Натальная карта | VedicWay",
    description: "Персональная ведическая натальная карта и её объяснение.",
    path: `/chart/${encodeURIComponent(chartId)}`,
    noindex: true,
  }), [chartId]);

  return (
    <Suspense fallback={<main className="route-loading" role="status">Загружаем рабочую область…</main>}>
      <ChartWorkspace chartId={chartId} onBackToLanding={() => onNavigate("/")} />
    </Suspense>
  );
}

function LandingSeam({ label }: { label?: string }) {
  return (
    <div
      className={`landing-seam ${label ? "landing-seam--labelled" : "landing-seam--ornament"}`}
      aria-hidden="true"
    >
      <span />
      {label && <b>{label}</b>}
      <span />
    </div>
  );
}

function LandingScreen({ onChartCreated, onNavigate, initialFormMode = "calculate" }: LandingScreenProps) {
  useEffect(() => {
    const origin = publicOrigin();
    return applySeo({
      title: initialFormMode === "recovery"
        ? "Восстановить оплаченный разбор | VedicWay"
        : "Натальная карта онлайн с персональным разбором | VedicWay",
      description: initialFormMode === "recovery"
        ? "Получите одноразовую ссылку на оплаченную натальную карту."
        : "Рассчитайте натальную карту онлайн по дате, точному времени и месту рождения. Получите наглядную карту и подробное персональное объяснение VedicWay.",
      path: initialFormMode === "recovery" ? "/access/recovery" : "/",
      noindex: initialFormMode === "recovery",
      structuredData: [
        {
          "@context": "https://schema.org",
          "@type": "Organization",
          "@id": `${origin}/about#organization`,
          name: "VedicWay",
          alternateName: "VedicWay.ru",
          legalName: "ИП Корольский Вадимир Васильевич",
          url: `${origin}/`,
          logo: `${origin}/assets/brand-mark.png`,
          email: "vedicway-ru@yandex.com",
          taxID: "722407070173",
          identifier: {
            "@type": "PropertyValue",
            propertyID: "ОГРНИП",
            value: "311723232700200",
          },
        },
        {
          "@context": "https://schema.org",
          "@type": "WebSite",
          "@id": `${origin}/#website`,
          name: "VedicWay",
          url: `${origin}/`,
          inLanguage: "ru-RU",
          publisher: { "@id": `${origin}/about#organization` },
        },
        {
          "@context": "https://schema.org",
          "@type": "WebApplication",
          "@id": `${origin}/#application`,
          name: "VedicWay",
          url: `${origin}/`,
          description: "Онлайн-расчёт ведической натальной карты по дате, времени и месту рождения.",
          applicationCategory: "LifestyleApplication",
          operatingSystem: "Web",
          inLanguage: "ru-RU",
          provider: { "@id": `${origin}/about#organization` },
        },
        {
          "@context": "https://schema.org",
          "@type": "FAQPage",
          "@id": `${origin}/#faq`,
          mainEntity: faqItems.map((item) => ({
            "@type": "Question",
            name: item.question,
            acceptedAnswer: {
              "@type": "Answer",
              text: item.answer,
            },
          })),
        },
      ],
    });
  }, [initialFormMode]);

  return (
    <>
      <SiteHeader active="home" onNavigate={onNavigate} variant="overlay" />
      <main className="site-main">
        <section className="hero" data-od-id="hero-screen">
        <div className="hero-scene" aria-hidden="true">
          <picture>
            <source srcSet="/assets/hero-space-light.avif" type="image/avif" />
            <source srcSet="/assets/hero-space-light.webp" type="image/webp" />
            <img
              className="hero-scene__background"
              src="/assets/hero-space-light.png"
              alt=""
              fetchPriority="high"
            />
          </picture>
          <AstrologyWheel />
        </div>

          <div className="hero-copy" aria-labelledby="hero-title" data-od-id="hero-copy">
          <h1 id="hero-title">
            <span>НАТАЛЬНАЯ КАРТА</span>{" "}
            <span className="hero-copy__accent">ОНЛАЙН</span>
          </h1>

          <p className="hero-copy__lead">
            Рассчитайте ведическую карту по дате, времени и месту рождения.
            Сервис покажет положения планет и объяснит их в рамках традиции джйотиш.
          </p>

          <div className="wisdom-note">
            <img src="/assets/celestial-star-light.png" alt="" />
            <p>
              Аянамша Лахири. Дома от лагны.
              <br />
              Результат зависит от точности времени рождения.
            </p>
          </div>

          <div className="social-proof" aria-label="Метод расчёта VedicWay">
            <div className="social-proof__copy">
              <div className="rating-line">
                <span>Проверяемый расчёт</span>
              </div>
              <p>Сидерические эфемериды и настройки рядом с результатом</p>
            </div>
          </div>
          </div>

          <BirthChartForm onChartCreated={onChartCreated} initialMode={initialFormMode} />
        </section>

        <LandingSeam label="Пример готового результата" />
        <ResultsShowcase />
        <LandingSeam />
        <FaqSection />
      </main>
    </>
  );
}

function chartIdFromPath(pathname: string) {
  const matched = pathname.match(/^\/chart\/([^/]+)$/);
  return matched ? decodeURIComponent(matched[1]) : null;
}

function rectificationIdFromPath(pathname: string) {
  const matched = pathname.match(/^\/rectification\/([^/]+)$/);
  return matched ? decodeURIComponent(matched[1]) : null;
}

function contentArticleFromPath(pathname: string) {
  const matched = pathname.match(/^\/(guide|blog)\/([^/]+)$/);
  if (!matched) return null;
  return {
    section: matched[1] as "guide" | "blog",
    slug: decodeURIComponent(matched[2]),
  };
}

const legalRoutes: Record<string, LegalDocumentKind> = {
  "/legal/offer": "terms",
  "/legal/privacy": "privacy",
  "/legal/user-agreement": "terms",
  "/legal/privacy-policy": "privacy",
  "/legal/personal-data-consent": "consent",
  "/legal/cookies": "cookies",
};

const trustRoutes: Record<string, TrustPageKind> = {
  "/about": "about",
  "/methodology": "methodology",
  "/editorial-policy": "editorial-policy",
  "/report-example": "report-example",
};

function App({ seoBootstrap = null }: { seoBootstrap?: SeoBootstrap | null }) {
  const [pathname, setPathname] = useState(() => window.location.pathname);

  useEffect(() => {
    const handlePopState = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    trackPageView(pathname);
  }, [pathname]);

  const navigate = (path: string) => {
    if (window.location.pathname === path) {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    window.history.pushState({}, "", path);
    setPathname(path);
    window.scrollTo({ top: 0 });
  };

  const openChart = (createdChartId: string) => {
    window.history.pushState({}, "", `/chart/${encodeURIComponent(createdChartId)}?tab=chart&varga=D1`);
    setPathname(`/chart/${createdChartId}`);
  };

  const chartId = chartIdFromPath(pathname);
  if (chartId) {
    return <ChartScreen chartId={chartId} onNavigate={navigate} />;
  }

  const rectificationId = rectificationIdFromPath(pathname);
  if (rectificationId) {
    return <RectificationFlow chartId={rectificationId} onNavigate={navigate} />;
  }

  if (pathname === "/guide") {
    const articles =
      seoBootstrap?.kind === "hub" && seoBootstrap.section === "guide"
        ? seoBootstrap.articles
        : undefined;
    return <GuidePage key="guide" onNavigate={navigate} initialArticles={articles} />;
  }
  if (pathname === "/blog") {
    const articles =
      seoBootstrap?.kind === "hub" && seoBootstrap.section === "blog"
        ? seoBootstrap.articles
        : undefined;
    return <BlogPage key="blog" onNavigate={navigate} initialArticles={articles} />;
  }
  if (pathname === "/access/recovery") {
    return <LandingScreen onNavigate={navigate} onChartCreated={openChart} initialFormMode="recovery" />;
  }
  if (pathname === "/access/confirm") return <RecoveryPage kind="confirm" onNavigate={navigate} />;
  if (pathname === "/privacy/request") return <RecoveryPage kind="privacy" onNavigate={navigate} />;

  const legalKind = legalRoutes[pathname];
  if (legalKind) return <LegalPage kind={legalKind} onNavigate={navigate} />;

  const trustKind = trustRoutes[pathname];
  if (trustKind) return <TrustPage kind={trustKind} onNavigate={navigate} />;

  const contentArticle = contentArticleFromPath(pathname);
  if (contentArticle) {
    const seededArticle =
      seoBootstrap?.kind === "article" &&
      seoBootstrap.section === contentArticle.section &&
      seoBootstrap.slug === contentArticle.slug
        ? seoBootstrap
        : null;
    return (
      <ArticlePage
        key={`${contentArticle.section}/${contentArticle.slug}`}
        section={contentArticle.section}
        slug={contentArticle.slug}
        onNavigate={navigate}
        initialArticle={seededArticle?.article}
        initialComments={seededArticle?.comments}
      />
    );
  }

  if (pathname !== "/") return <NotFoundPage onNavigate={navigate} />;

  return <LandingScreen onNavigate={navigate} onChartCreated={openChart} />;
}

export default App;
