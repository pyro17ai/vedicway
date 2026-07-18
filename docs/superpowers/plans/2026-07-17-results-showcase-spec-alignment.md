# Results Showcase Spec Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перестроить второй блок лендинга в интерактивную демонстрацию результата, которая совпадает с PyJHora UI-спецификацией и закрывает семь browser annotations.

**Architecture:** Контрольный snapshot живёт в отдельном типизированном fixture-модуле. Южноиндийская D1 строится семантической HTML/CSS-сеткой, а `ResultsShowcase` управляет вкладками и локальными раскрытиями. Три специальные пиктограммы остаются единственными новыми raster-активами.

**Tech Stack:** React 19, TypeScript 7, Vite 8, Vitest, Testing Library, GSAP 3, CSS.

## Global Constraints

- Backend и реальные MCP-вызовы не подключаются.
- Источник истины для D1: контрольные значения get_rasi_chart из локальной спецификации.
- Геометрия: только fixed-sign South Indian 4×4.
- Крупные растровые изображения с текстом запрещены; новые raster-активы ограничены тремя rail-иконками.
- Текущие пользовательские изменения вне второго блока не трогать и не коммитить.

---

### Task 1: Regression contract for authentic demo data

**Files:**
- Create: `src/components/results-demo-data.ts`
- Create: `src/components/NatalChartGraphic.test.tsx`
- Modify: `src/components/ResultsShowcase.test.tsx`

**Interfaces:**
- Produces: `demoChartSnapshot`, `southIndianCells`, `classicalDrishtiRows`.
- Consumes: exact control values from the PyJHora UI specification.

- [ ] **Step 1: Write failing tests**

Assert that the grid exposes twelve signs, twelve objects, Lagna in Scorpio, Moon and Saturn in Cancer, Sun/Venus/Ketu in Virgo, Mars/Mercury/Jupiter in Libra and Rahu in Pisces. Assert that no profile dropdown, western aspect names or old elemental summary remains.

- [ ] **Step 2: Run tests to verify RED**

Run: `npm run test:run -- src/components/NatalChartGraphic.test.tsx src/components/ResultsShowcase.test.tsx`
Expected: failures for missing fixture, old chart values and the existing profile.

- [ ] **Step 3: Add typed fixture and South Indian mapping**

Create explicit `rasiIndex`, `sign`, `degree`, `nakshatra`, `pada`, `isOuter` fields. Derive house labels only through `((rasiIndex - 7 + 12) % 12) + 1` and label them `whole-sign`.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run the same focused command and require zero failures.

### Task 2: Generated rail icons and polished navigation

**Files:**
- Create: `public/assets/results-nav-chart.png`
- Create: `public/assets/results-nav-explanation.png`
- Create: `public/assets/results-nav-questions.png`
- Modify: `src/components/ResultsShowcase.tsx`
- Modify: `src/styles.css`

**Interfaces:**
- Consumes: three transparent PNG assets.
- Produces: `resultTabs` with `iconSrc`, accessible labels and unchanged keyboard behavior.

- [ ] **Step 1: Extend the failing UI test**

Assert that each tab contains the expected generated image path and that active state retains `aria-selected=true`.

- [ ] **Step 2: Generate each icon separately**

Use GPT Image on a flat `#00ff00` background, remove the key with the imagegen helper, validate alpha and copy the files into `public/assets`.

- [ ] **Step 3: Replace Lucide rail symbols and refine active state**

Use a thin inset copper line, low-opacity radial wash and a narrow halo. Keep 44 px minimum touch targets and visible focus.

- [ ] **Step 4: Run focused tests**

Run `npm run test:run -- src/components/ResultsShowcase.test.tsx` and require zero failures.

### Task 3: Authentic chart, explanations and question interactions

**Files:**
- Modify: `src/components/NatalChartGraphic.tsx`
- Modify: `src/components/ResultsShowcase.tsx`
- Modify: `src/styles.css`

**Interfaces:**
- Consumes: `demoChartSnapshot`, `southIndianCells`, `classicalDrishtiRows`.
- Produces: chart cells with detail popover, real summary fields, inner tabs, expandable explanations and topic-filtered questions.

- [ ] **Step 1: Add failing interaction tests**

Test detail-cell selection, `Подробнее` source disclosure, `Вернуться к карте`, question filters, facts disclosure and custom-question state.

- [ ] **Step 2: Implement chart and data panels**

Keep the D1 at 520–560 px, remove every negative overlap margin and render the four authentic summary facts. Mark Uranus, Neptune and Pluto as additional snapshot objects.

- [ ] **Step 3: Implement grounded explanations and questions**

Every expanded explanation names its facts and source. Questions use only values present in the fixture; missing dasha or strength data produces `Недостаточно данных` with a named required calculation.

- [ ] **Step 4: Verify focused and full tests**

Run `npm run test:run` and require zero failures.

### Task 4: Responsive polish and browser acceptance

**Files:**
- Modify: `src/styles.css`
- Modify: `docs/results-showcase/design-contract.md`

**Interfaces:**
- Produces: stable layouts at desktop, tablet and mobile widths.

- [ ] **Step 1: Add the transition divider**

Render `ПРИМЕР ГОТОВОГО РЕЗУЛЬТАТА` between hero and result with two subtle hairlines and no new CTA.

- [ ] **Step 2: Build and inspect**

Run `npm run build`, start Vite, then inspect 1672×941, 1569×920, 1024×768 and 390×844.

- [ ] **Step 3: Exercise interaction paths**

Click all three rail tabs, switch with Arrow/Home/End, open an explanation, change a detail tab, filter a question and disclose facts. Check console errors and horizontal overflow.

- [ ] **Step 4: Record final evidence**

Capture fresh screenshots under `artifacts/` and update the quality checklist only after every command exits successfully.
