import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

gsap.registerPlugin(useGSAP);

const CENTER = 400;
const PRIMARY_RADII = [382, 367, 338, 286, 236, 176, 92];
const ZODIAC_SIGNS = [
  "\u2648\uFE0E",
  "\u2649\uFE0E",
  "\u264A\uFE0E",
  "\u264B\uFE0E",
  "\u264C\uFE0E",
  "\u264D\uFE0E",
  "\u264E\uFE0E",
  "\u264F\uFE0E",
  "\u2650\uFE0E",
  "\u2651\uFE0E",
  "\u2652\uFE0E",
  "\u2653\uFE0E",
];

function polarPoint(radius: number, angleDegrees: number) {
  const angle = ((angleDegrees - 90) * Math.PI) / 180;

  return {
    x: CENTER + Math.cos(angle) * radius,
    y: CENTER + Math.sin(angle) * radius,
  };
}

function pointsForRadius(radius: number, offset = 0) {
  return Array.from({ length: 12 }, (_, index) => {
    const point = polarPoint(radius + (index % 3) * offset, index * 30);
    return `${point.x},${point.y}`;
  }).join(" ");
}

export function AstrologyWheel() {
  const scopeRef = useRef<HTMLDivElement>(null);
  const wheelRef = useRef<SVGSVGElement>(null);

  useGSAP(
    () => {
      const media = gsap.matchMedia();

      media.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.to(wheelRef.current, {
          rotation: 360,
          transformOrigin: "50% 50%",
          duration: 90,
          repeat: -1,
          ease: "none",
        });
      });

      return () => media.revert();
    },
    { scope: scopeRef },
  );

  return (
    <div ref={scopeRef} className="astrology-wheel-shell" aria-hidden="true">
      <svg
        ref={wheelRef}
        className="astrology-wheel"
        data-testid="astrology-wheel"
        aria-hidden="true"
        focusable="false"
        viewBox="0 0 800 800"
      >
        <g className="astrology-wheel__rings" fill="none" stroke="currentColor">
          {PRIMARY_RADII.map((radius, index) => (
            <circle
              key={radius}
              cx={CENTER}
              cy={CENTER}
              r={radius}
              opacity={index < 2 ? 0.82 : 0.46}
              strokeWidth={index < 2 ? 1.25 : 0.8}
            />
          ))}
        </g>

        <g className="astrology-wheel__spokes" fill="none" stroke="currentColor">
          {Array.from({ length: 12 }, (_, index) => {
            const inner = polarPoint(92, index * 30);
            const outer = polarPoint(382, index * 30);

            return (
              <line
                key={`spoke-${index}`}
                data-spoke
                x1={inner.x}
                y1={inner.y}
                x2={outer.x}
                y2={outer.y}
                opacity="0.58"
                strokeWidth="0.9"
              />
            );
          })}

          {Array.from({ length: 36 }, (_, index) => {
            const angle = index * 10;
            const inner = polarPoint(index % 3 === 0 ? 236 : 286, angle);
            const outer = polarPoint(338, angle);

            return (
              <line
                key={`ray-${index}`}
                x1={inner.x}
                y1={inner.y}
                x2={outer.x}
                y2={outer.y}
                opacity={index % 3 === 0 ? 0.36 : 0.19}
                strokeWidth="0.65"
              />
            );
          })}
        </g>

        <g fill="none" stroke="currentColor" strokeWidth="0.75">
          <polygon points={pointsForRadius(236, 24)} opacity="0.36" />
          <polygon points={pointsForRadius(176, 42)} opacity="0.28" />
          {Array.from({ length: 72 }, (_, index) => {
            const angle = index * 5;
            const inner = polarPoint(index % 6 === 0 ? 367 : 373, angle);
            const outer = polarPoint(382, angle);

            return (
              <line
                key={`tick-${index}`}
                x1={inner.x}
                y1={inner.y}
                x2={outer.x}
                y2={outer.y}
                opacity={index % 6 === 0 ? 0.72 : 0.35}
              />
            );
          })}
        </g>

        <g
          className="astrology-wheel__signs"
          fill="currentColor"
          fontFamily="Segoe UI Symbol, Times New Roman, serif"
          fontSize="28"
          textAnchor="middle"
        >
          {ZODIAC_SIGNS.map((sign, index) => {
            const point = polarPoint(350, index * 30 + 15);

            return (
              <text
                key={sign}
                x={point.x}
                y={point.y}
                dy="0.35em"
                opacity="0.72"
                transform={`rotate(${index * 30 + 15} ${point.x} ${point.y})`}
              >
                {sign}
              </text>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
