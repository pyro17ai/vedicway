import { useEffect, useState } from "react";

import { AstrologyWheel } from "./components/AstrologyWheel";
import { AdminPage } from "./components/AdminPage";
import { ArticlePage } from "./components/ArticlePage";
import { BirthChartForm } from "./components/BirthChartForm";
import { ChartWorkspace } from "./components/ChartWorkspace";
import { FaqSection } from "./components/FaqSection";
import { GuidePage } from "./components/GuidePage";
import { LegalPage, type LegalDocumentKind } from "./components/LegalPage";
import { ResultsShowcase } from "./components/ResultsShowcase";
import { SiteHeader } from "./components/SiteHeader";

const avatars = [
  "/assets/avatar-01.png",
  "/assets/avatar-02.png",
  "/assets/avatar-03.png",
  "/assets/avatar-04.png",
];

type LandingScreenProps = {
  onChartCreated: (chartId: string) => void;
  onNavigate: (path: string) => void;
};

function LandingSeam({ label }: { label?: string }) {
  return (
    <div className="landing-seam" aria-hidden="true">
      <span />
      {label && <b>{label}</b>}
      <span />
    </div>
  );
}

function LandingScreen({ onChartCreated, onNavigate }: LandingScreenProps) {
  useEffect(() => {
    document.title = "VedicWay - натальная карта";
    let canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.append(canonical);
    }
    canonical.href = window.location.origin;
  }, []);

  return (
    <>
      <SiteHeader active="home" onNavigate={onNavigate} variant="overlay" />
      <main className="site-main">
        <section className="hero" data-od-id="hero-screen">
        <div className="hero-scene" aria-hidden="true">
          <img
            className="hero-scene__background"
            src="/assets/hero-space.png"
            alt=""
            fetchPriority="high"
          />
          <AstrologyWheel />
        </div>

          <div className="hero-copy" aria-labelledby="hero-title" data-od-id="hero-copy">
          <h1 id="hero-title">
            <span>ПОЗНАЙ СЕБЯ</span>
            <span className="hero-copy__accent">ЧЕРЕЗ КОСМОС</span>
          </h1>

          <p className="hero-copy__lead">
            Натальная карта раскрывает ваш уникальный рисунок судьбы.
            Узнайте своё предназначение и скрытые ресурсы.
          </p>

          <div className="wisdom-note">
            <img src="/assets/celestial-star.png" alt="" />
            <p>
              Древняя мудрость. Современные технологии.
              <br />
              Персональный подход.
            </p>
          </div>

          <div className="social-proof" aria-label="Оценка сервиса 4,9 из 5">
            <div className="avatar-stack" aria-hidden="true">
              {avatars.map((avatar, index) => (
                <img
                  key={avatar}
                  data-avatar
                  src={avatar}
                  alt=""
                  style={{ zIndex: avatars.length - index }}
                />
              ))}
            </div>

            <div className="social-proof__copy">
              <div className="rating-line">
                <span>4.9 из 5</span>
                <span className="rating-stars" aria-hidden="true">
                  ★★★★★
                </span>
              </div>
              <p>более 18 000 карт построено</p>
            </div>
          </div>
          </div>

          <BirthChartForm onChartCreated={onChartCreated} />
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

function guideSlugFromPath(pathname: string) {
  const matched = pathname.match(/^\/guide\/([^/]+)$/);
  if (!matched || matched[1] === "editor") return null;
  return decodeURIComponent(matched[1]);
}

const legalRoutes: Record<string, LegalDocumentKind> = {
  "/legal/user-agreement": "terms",
  "/legal/privacy-policy": "privacy",
  "/legal/personal-data-consent": "consent",
  "/legal/cookies": "cookies",
};

function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname);

  useEffect(() => {
    const handlePopState = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigate = (path: string) => {
    if (window.location.pathname === path) {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    window.history.pushState({}, "", path);
    setPathname(path);
    window.scrollTo({ top: 0 });
  };

  const chartId = chartIdFromPath(pathname);
  if (chartId) {
    return <ChartWorkspace chartId={chartId} onBackToLanding={() => {
      navigate("/");
    }} />;
  }

  if (pathname === "/admin" || pathname.startsWith("/admin/")) return <AdminPage onNavigate={navigate} />;
  if (pathname === "/guide") return <GuidePage onNavigate={navigate} />;

  const legalKind = legalRoutes[pathname];
  if (legalKind) return <LegalPage kind={legalKind} onNavigate={navigate} />;

  const guideSlug = guideSlugFromPath(pathname);
  if (guideSlug) return <ArticlePage slug={guideSlug} onNavigate={navigate} />;

  return <LandingScreen onNavigate={navigate} onChartCreated={(createdChartId) => {
    window.history.pushState({}, "", `/chart/${encodeURIComponent(createdChartId)}?tab=chart&varga=D1&mode=plain`);
    setPathname(`/chart/${createdChartId}`);
  }} />;
}

export default App;
