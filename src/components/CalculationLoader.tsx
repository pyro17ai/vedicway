import { useRef, type CSSProperties, type ElementType } from "react";
import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import { BookOpen, CircleHelp, Clock3 } from "lucide-react";

type CalculationLoaderVariant = "chart" | "explanation" | "questions" | "rectification";

type CalculationLoaderProps = {
  variant: CalculationLoaderVariant;
  className?: string;
};

const loaderCopy: Record<CalculationLoaderVariant, {
  kicker: string;
  title: string;
  description: string;
  note: string;
}> = {
  chart: {
    kicker: "РАСЧЁТ D1",
    title: "Строим натальную карту",
    description: "Вычисляем положения планет и собираем двенадцать домов вокруг лагны.",
    note: "Карта появится здесь автоматически",
  },
  explanation: {
    kicker: "ПЕРВОЕ ЧТЕНИЕ И ВОПРОСЫ",
    title: "Готовим объяснение и вопросы",
    description: "Одновременно связываем положения карты с жизненными темами и составляем вопросы для личного наблюдения.",
    note: "Оба раздела появятся здесь автоматически",
  },
  questions: {
    kicker: "ПЕРВОЕ ЧТЕНИЕ И ВОПРОСЫ",
    title: "Готовим объяснение и вопросы",
    description: "Одновременно связываем положения карты с жизненными темами и составляем вопросы для личного наблюдения.",
    note: "Оба раздела появятся здесь автоматически",
  },
  rectification: {
    kicker: "РАСЧЁТ ИДЁТ",
    title: "Сопоставляем варианты времени",
    description: "Сверяем временные кандидаты с событиями анкеты и проверяем устойчивость результата.",
    note: "Результат появится здесь автоматически",
  },
};

function indexedStyle(index: number) {
  return { "--loader-index": index } as CSSProperties;
}

function ChartVisual() {
  return (
    <div className="calculation-loader__visual calculation-loader__chart" aria-hidden="true">
      {Array.from({ length: 12 }).map((_, index) => (
        <span key={index} style={indexedStyle(index)} />
      ))}
    </div>
  );
}

function ExplanationVisual() {
  return (
    <div className="calculation-loader__visual calculation-loader__explanation" aria-hidden="true">
      <div className="calculation-loader__facts">
        {Array.from({ length: 4 }).map((_, index) => <span key={index} style={indexedStyle(index)} />)}
      </div>
      <div className="calculation-loader__book"><BookOpen /></div>
      <div className="calculation-loader__themes">
        {Array.from({ length: 4 }).map((_, index) => <span key={index} style={indexedStyle(index)} />)}
      </div>
    </div>
  );
}

function QuestionsVisual() {
  return (
    <div className="calculation-loader__visual calculation-loader__questions" aria-hidden="true">
      {Array.from({ length: 4 }).map((_, index) => (
        <span key={index} style={indexedStyle(index)}>
          <CircleHelp />
          <i />
          <i />
        </span>
      ))}
    </div>
  );
}

function RectificationVisual() {
  return (
    <div className="calculation-loader__visual calculation-loader__rectification" aria-hidden="true">
      <div className="calculation-loader__dial">
        <Clock3 />
        {Array.from({ length: 8 }).map((_, index) => <span key={index} style={indexedStyle(index)} />)}
      </div>
      <div className="calculation-loader__candidates">
        {["I", "II", "III", "IV", "V"].map((label, index) => (
          <span key={label} style={indexedStyle(index)}>{label}</span>
        ))}
      </div>
    </div>
  );
}

function LoaderVisual({ variant }: { variant: CalculationLoaderVariant }) {
  if (variant === "chart") return <ChartVisual />;
  if (variant === "explanation") return <ExplanationVisual />;
  if (variant === "questions") return <QuestionsVisual />;
  return <RectificationVisual />;
}

gsap.registerPlugin(useGSAP);

export function CalculationLoader({ variant, className = "" }: CalculationLoaderProps) {
  const root = useRef<HTMLElement>(null);
  const copy = loaderCopy[variant];
  const Heading: ElementType = variant === "rectification" ? "h1" : "h2";

  useGSAP(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    gsap.fromTo(
      ".calculation-loader__animate",
      { autoAlpha: 0, y: 6 },
      {
        autoAlpha: 1,
        y: 0,
        duration: 0.24,
        stagger: 0.055,
        ease: "power3.out",
        clearProps: "transform,opacity,visibility",
      },
    );
  }, { scope: root });

  return (
    <section
      ref={root}
      className={`calculation-loader calculation-loader--${variant}${className ? ` ${className}` : ""}`}
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-busy="true"
    >
      <LoaderVisual variant={variant} />
      <div className="calculation-loader__copy">
        <span className="calculation-loader__kicker calculation-loader__animate">{copy.kicker}</span>
        <Heading className="calculation-loader__animate">{copy.title}</Heading>
        <p className="calculation-loader__animate">{copy.description}</p>
        <div className="calculation-loader__note calculation-loader__animate">
          <span aria-hidden="true" />
          {copy.note}
        </div>
      </div>
    </section>
  );
}
