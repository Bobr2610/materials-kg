---
name: ""
overview: ""
todos: []
isProject: false
---

# Plan: R&D в AI 2026 + AI-First (red_mad_robot) — final validation (latest pass 2026-03-27)

## Validation log

- **Pass 2 (same day, post line-count drift):** `grep` по `docs/research/20260325*.md` для `jTKhg1jqF_M` и `youtube.com/watch` — **0** совпадений; P0 YouTube **ещё не внесён**. Методология: посты **5145/5146/5170** в теле и в `## Источники` (рядом ~1200–1202, ориентир — **якоря**, не номера строк). YouTube URL — повторный **fetch**, страница открывается.

## Deep research (primary sources) — re-checked


| Source                                                                   | Status                       | Notes                                                                                                                                    |
| ------------------------------------------------------------------------ | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| [YouTube — «Ноосфера» #129](https://www.youtube.com/watch?v=jTKhg1jqF_M) | **Resolves** (fetch, pass 2) | Илья Самофеев, red_mad_robot; AI-First / AI-Native; продукт, процессы, люди, технологическая готовность; агентизация, стоимость токенов. |
| [t.me/Redmadnews/5170](https://t.me/Redmadnews/5170)                     | В комплекте                  | Анонс подкаста в канале; в методологии — основной вход в теле (`### Публичные ориентиры рынка…`).                                        |
| [t.me/Redmadnews/5146](https://t.me/Redmadnews/5146)                     | В комплекте                  | Серия «R&D в AI в 2026»; без именованного пересказа карточек в теле.                                                                     |


**Инвариант:** YouTube остаётся **рекомендуемым вторым первоисточником** рядом с 5170 для договорной/аудиторской трассируемости (один смысл — два URL с разными ролями).

---

## Final validation vs `docs/research/20260325-*.md`


| Item                                                                 | Status              | Evidence                                                                                                                                                                                            |
| -------------------------------------------------------------------- | ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `### Публичные ориентиры рынка (@Redmadnews, 2026)` + 5145/5146/5170 | **Done**            | [methodology](docs/research/20260325-research-report-methodology-main-ru.md) якорь `#method_market_benchmarks_2026`; кросс-ссылка из резюме TOM на этот подраздел (без дублирования списка постов). |
| Источники methodology: 5145, 5146, 5170                              | **Done**            | Три отдельные строки в `## Источники` (СП/фабрика, R&D 2026, AI-first подкаст).                                                                                                                     |
| Sizing: 5159 + «три мира»                                            | **Done**            | [sizing](docs/research/20260325-research-report-sizing-economics-main-ru.md) тело + `## Источники`.                                                                                                 |
| Appendix A: посты Redmadnews + Habr MCP + GitHub                     | **Done**            | [appendix-a](docs/research/20260325-research-appendix-a-index-ru.md); строка навигации в таблице соответствия → методология `#…publichnye_orientiry…`.                                              |
| **YouTube** в `20260325-*.md`                                        | **Not done**        | grep `jTKhg1jqF_M` / `youtube.com` по `20260325*.md` — **0** совпадений. **Единственный оставшийся P0 по этому плану.**                                                                             |
| Sizing `## Источники`: дубликат строки канала @Redmadnews            | **Resolved**        | В списке источников **одна** строка канала (`@Redmadnews … исследований`); второй хит — только тело/вводный «Источник:» в другом разделе, не дубль bullet.                                          |
| Именованный синтез (Рыжков, Малых, …) + DLM                          | **Optional Tier 2** | По-прежнему не внесён; закрывается ссылкой на 5146.                                                                                                                                                 |
| Appendix B/C/D расширения под карточки                               | **Optional**        | Не требуются для закрытия минимального трека.                                                                                                                                                       |


**Итог:** ядро интеграции **выполнено**; план сведён к **одному обязательному хвосту (YouTube в реестрах)** и опциональному Tier 2.

---

## Связь с другими планами (актуально)

- **[cmo-genai-research-pack-update-validated.plan.md](cmo-genai-research-pack-update-validated.plan.md)** — CMO Club × red_mad_robot **реализован** в том же комплекте; ортогонален R&D-карточкам.
- **[research-redmadnews-digest-pack-update.plan.md](research-redmadnews-digest-pack-update.plan.md)** — Tier A/B по Redmadnews **закрыты** в репозитории; отдельные хвосты (optional parity, 20260323 baseline) там, не здесь.
- **[research-org-strategy-skolkovo-redmadrobot.plan.md](research-org-strategy-skolkovo-redmadrobot.plan.md)** — Skolkovo cdto уже **перекрёстно** упомянут в методологии рядом с Redmadnews-блоком; не дублировать тезисы AI-First без согласования.
- **[openai-enterprise-report-research-pack.plan.md](openai-enterprise-report-research-pack.plan.md)** — отдельный трек (OpenAI State of Enterprise AI); **не смешивать** с red_mad_robot / R&D 2026 без явного кросс-линка по смыслу.

---

## Оставшаяся работа

### P0 (единственный обязательный по данному плану)

- Добавить [YouTube — Ноосфера #129, Самофеев (AI-First)](https://www.youtube.com/watch?v=jTKhg1jqF_M) в:
  - [methodology](docs/research/20260325-research-report-methodology-main-ru.md) `## Источники` (рядом с пунктом про 5170; в теле опционально одна фраза «полный выпуск — YouTube»);
  - [appendix-a](docs/research/20260325-research-appendix-a-index-ru.md) **оба** блока: сводные источники + `## Полный реестр` (например подсекция «Подкасты / видео» или рядом с Telegram-постами).

### P1 (optional)

- У 5146: список организаций серии + одна осторожная строка про DLM как НИОКР-горизонт.
- Appendix B/C/D — только по явному запросу заказчика.

### Не делать

- Дублировать `### Публичные ориентиры рынка` между `#r_d_praktiki` и `#issledovaniya_marta_2026`.

---

## После правок P0

- Проверить [AGENTS.md](docs/research/AGENTS.md): пустая строка перед списками; plain links в `## Источники`.
- Ruff/pytest: N/A.

---

## Todos

- P0: YouTube URL → methodology Источники + appendix A (сводный + полный реестр)
- P0: dedup @Redmadnews в sizing Источники — **уже выполнено в текущем репозитории**
- P1: опционально имена + DLM; B/C/D
- Синхронизация с digest/CMO планами — **отражена выше** (отдельные файлы)

