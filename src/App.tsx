import { AstrologyWheel } from "./components/AstrologyWheel";
import { BirthChartForm } from "./components/BirthChartForm";

const avatars = [
  "/assets/avatar-01.png",
  "/assets/avatar-02.png",
  "/assets/avatar-03.png",
  "/assets/avatar-04.png",
];

function App() {
  return (
    <main className="hero" data-od-id="hero-screen">
      <div className="hero-scene" aria-hidden="true">
        <img
          className="hero-scene__background"
          src="/assets/hero-space.png"
          alt=""
          fetchPriority="high"
        />
        <AstrologyWheel />
      </div>

      <header className="brand" data-od-id="brand">
        <img className="brand__mark" src="/assets/brand-mark.png" alt="" />
        <span className="brand__name">VedicWay</span>
      </header>

      <section className="hero-copy" aria-labelledby="hero-title" data-od-id="hero-copy">
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
      </section>

      <BirthChartForm />
    </main>
  );
}

export default App;
