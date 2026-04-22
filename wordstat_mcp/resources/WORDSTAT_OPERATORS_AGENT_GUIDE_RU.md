# Wordstat Operators Guide for AI Agents

Source: [Yandex Wordstat, Operators](https://yandex.com/support2/wordstat/en/content/operators).

## Purpose

Use this guide when a user describes a Wordstat request in natural language and an MCP tool requires a `phrase` value. Your job is to infer the search intent, choose the right Wordstat operators, and pass an already marked-up phrase to the API.

In this MCP server, the client passes `phrases`, but each list item is sent to Yandex Wordstat API as a separate `phrase` field. One phrase is validated as a non-empty string with a maximum length of 400 characters.

## MCP Integration Contract

The server exposes this guidance in three ways:

- MCP resource: `wordstat://operators/agent-guide`
- MCP prompt: `wordstat_phrase_builder`
- MCP tool: `build_wordstat_phrase`

Use the prompt or resource as agent context before calling Wordstat tools. Then
call `build_wordstat_phrase` with the parsed base phrase and intent hints. Use
the returned `phrase` in `getTop`, `getDynamics`, or `getRegionsDistribution`.

Important: MCP prompts and resources cannot force a consuming LLM to follow
them. They are discoverable context provided by the server. Hard requirements
must be enforced in server tools. This server therefore rejects unsupported
operators in `getDynamics` and returns machine-readable warning codes from
`build_wordstat_phrase` when requested operators are not compatible with the
target method.

## Supported Operators

Wordstat supports the operators `!`, `+`, `" "`, `[]`, `()`, and `|`. Operators can be combined when the selected Wordstat method supports that combination.

| Operator | Meaning | Keyword phrase example | Matching queries | Non-matching queries |
| --- | --- | --- | --- | --- |
| `!` | Fixes the exact word form: case, number, tense, or another grammatical form. | `купить !собаку` | `купить собаку` | `купить корм для собак`, `купить собаки` |
| `+` | Forces Wordstat to include a stop word such as a preposition, pronoun, particle, or another service word that may otherwise be ignored. | `работа +из дома` | `работа из дома` | `работа дома`, `работа на дому` |
| `" "` | Fixes the exact number of words. Extra words are not allowed, but word forms and word order may still vary. | `"купить авто"` | `купить авто`, `авто купить` | `купить красное авто` |
| `[]` | Fixes word order inside the brackets. Word forms and stop words inside the brackets follow Wordstat rules. | `билеты [из москвы в париж]` | `билеты из москвы в париж`, `авиабилеты из москвы в париж` | `билеты из парижа в москву`, `билеты москва париж`, `билеты из москвы в CDG париж` |
| `()` and `|` | Groups alternatives in a complex query. The vertical bar means "or". | `заказать (суши|пиццу)` | `заказать суши`, `заказать пиццу` | Queries without one of the grouped alternatives |

## MCP Method Limits

- `getTop`: all operators can be used. Use this method for popular queries, related keywords, and phrase expansion.
- `getRegionsDistribution`: all operators can be used. Use this method to compare demand by regions or cities.
- `getDynamics`: use only the `+` operator. Wordstat dynamics supports only forced inclusion of stop words.
- `find_regions`, `getRegionsTree`, `update_regions_tree`, `wordstat_env_health`: these tools do not accept search phrases and do not need operators. Use `find_regions` for user-provided city or region names; use `getRegionsTree` only for bulk/debug region index lookup.

If the user asks for dynamics for an exact phrase, fixed word order, fixed word forms, or grouped alternatives, do not add `" "`, `[]`, `!`, `()`, or `|` to `phrase` for `getDynamics`. Keep this compatibility detail internal unless the user asks about query syntax, exactness, or why the phrase changed. Use either a plain phrase or only `+` for meaningful stop words.

## Warning Codes

`build_wordstat_phrase` returns warning codes for agent control flow. Do not
quote or explain these codes to the user during normal keyword, dynamics, or
region-analysis flows.

| Code | Meaning | Default user-facing behavior |
| --- | --- | --- |
| `BASE_PHRASE_INFERRED` | `base_phrase` was inferred from `natural_query` by simple server-side heuristics. | Keep internal unless the inferred phrase looks wrong or `needs_review` is true. |
| `DYNAMICS_OPERATOR_LIMIT` | Requested exact-count, fixed-order, or fixed-form operators were omitted for `getDynamics`. | Keep internal unless the user asks about exactness or query syntax. |
| `DYNAMICS_OPERATORS_STRIPPED` | Unsupported operators were removed from a `getDynamics` phrase. | Keep internal unless the removed operators materially change interpretation. |

## Operator Selection Algorithm

1. Identify the Wordstat method from the user's task.
2. Extract the base search phrase and remove command words. For example, from "посмотри частотность купить тур в турцию", use `купить тур в турцию`.
3. Detect whether the user needs a fixed word form, exact word count, fixed word order, mandatory stop word, or alternatives.
4. Check method limits. For `getDynamics`, keep only `+` when needed.
5. Build `phrase` with the smallest necessary set of operators. Do not add operators "just in case".
6. If intent is ambiguous, prefer a less restrictive phrase. An overly strict phrase can undercount demand.
7. Do not escape operators or replace them with words. The `phrase` value must contain the operator characters themselves.

## Usage Rules

### Operator `!`

Use `!` when the user asks to preserve a specific grammatical form:

- "only this form"
- "exactly singular"
- "do not include plural forms"
- "fix this word form"

Examples:

| User intent | `phrase` |
| --- | --- |
| Get statistics exactly for the word form "собаку" | `купить !собаку` |
| Count only the form "купил", not "купить" or "куплю" | `!купил телефон` |
| Fix both important forms | `!купить !собаку` |

Do not put `!` before every word automatically. Fix only the words where the form matters.

### Operator `+`

Use `+` when a service word changes the phrase meaning and must be counted:

- prepositions: `в`, `на`, `из`, `с`, `для`, `от`, `до`, `под`
- particles or conjunctions when they are semantically important
- pronouns when they are part of the query

Examples:

| User intent | `phrase` |
| --- | --- |
| Work specifically "из дома" | `работа +из дома` |
| Delivery specifically "на дом" | `доставка +на дом` |
| Phrase specifically "из Москвы в Париж" without fixed word order | `билеты +из москвы +в париж` |

For `getDynamics`, this is the only operator that should be applied.

### Operator `" "`

Use quotation marks when the user wants the phrase without extra words:

- "exact phrase"
- "without extra words"
- "exactly these words"
- "count only this two-word query"

Examples:

| User intent | `phrase` |
| --- | --- |
| Only two words, "купить авто", without modifiers | `"купить авто"` |
| Only "ремонт квартир", without city or attributes | `"ремонт квартир"` |
| Exact three-word phrase | `"купить тур онлайн"` |

Quotation marks fix the number of words, but not necessarily word order or grammatical form. If order matters, use `[]`.

### Operator `[]`

Use square brackets when word order is important:

- routes: `из A в B`
- comparisons: `A против B`
- phrases where reordering changes meaning
- the user explicitly says "in this order"

Examples:

| User intent | `phrase` |
| --- | --- |
| Route phrase "из Москвы в Париж" | `билеты [из москвы в париж]` |
| Comparison phrase "айфон против самсунг" | `[айфон против самсунг]` |
| Phrase "купить билет онлайн" must keep this order | `[купить билет онлайн]` |

If both exact word count and word order are needed, combine quotation marks and square brackets carefully. Usually `[]` is enough for order, and `" "` is enough for excluding extra words. Do not over-constrain the query without an explicit requirement.

### Operators `()` and `|`

Use grouping when the user lists alternatives:

- "суши или пицца"
- "айфон 15 или айфон 16"
- "купить или заказать"
- "для Москвы и Санкт-Петербурга" only if these are phrase alternatives, not API regions

Examples:

| User intent | `phrase` |
| --- | --- |
| Alternative phrase "суши или пицца" | `заказать (суши|пиццу)` |
| Alternative phrase "айфон 15 или айфон 16" | `купить айфон (15|16)` |
| Alternative phrase "ноутбук или компьютер" | `ремонт (ноутбука|компьютера)` |

If alternatives can be sent as separate items in `phrases`, prefer separate phrases when the user expects separate statistics:

```json
{
  "phrases": ["заказать суши", "заказать пиццу"]
}
```

Use grouping when the user wants one combined query that covers all variants.

## Combining Operators

Operators can be combined, but every operator must have a reason.

| Intent | `phrase` | Reason |
| --- | --- | --- |
| Exact word count and mandatory preposition | `"работа +из дома"` | Quotes limit the word count; `+` preserves `из`. |
| Route with fixed direction | `билеты [+из москвы +в париж]` | `[]` fixes order; `+` preserves prepositions. |
| Product alternatives with a fixed word form | `купить !телефон (айфон|самсунг)` | `!` fixes the word form; grouping sets alternatives. |
| Exact phrase with a specific word form | `"купить !собаку"` | No extra words; the form `собаку` is fixed. |

## Natural Language Transformations

| User request | Method | `phrase` |
| --- | --- | --- |
| "Найди топ запросов по покупке авто" | `getTop` | `купить авто` |
| "Покажи топ по точной фразе купить авто" | `getTop` | `"купить авто"` |
| "Сравни регионы для билетов из Москвы в Париж; порядок важен" | `getRegionsDistribution` | `билеты [+из москвы +в париж]` |
| "Покажи динамику работы из дома" | `getDynamics` | `работа +из дома` |
| "Покажи динамику точной фразы купить авто" | `getDynamics` | `купить авто` |
| "Посмотри спрос на суши или пиццу" | `getTop` | `(суши|пицца)` |
| "Нужна статистика по форме собаку, не собак" | `getTop` | `!собаку` |

## Preflight Check Before Calling API

Before calling an MCP tool, check:

- `phrase` is not empty.
- `phrase` is not longer than 400 characters.
- For `getDynamics`, `phrase` contains no operators except `+`.
- Regional words do not replace the `regions` parameter when the user explicitly means a geographic filter. For example, for "в Москве", call `find_regions` first and use returned `regions` IDs instead of adding `москва` to `phrase`.
- If the user needs separate statistics for several phrases, pass several items in `phrases` instead of one phrase with `|`.
- If the user needs combined statistics for alternatives, `()` and `|` can be used.

## User-Facing Response Guidance

When an operator change materially affects user interpretation, briefly state
which phrase you are sending. Otherwise keep operator-normalization details
internal and focus on the returned data.

```text
Using phrase: "работа +из дома" so Wordstat includes the preposition "из".
```

For unsupported operator combinations in dynamics, usually omit the limitation
from the final answer. Mention it only when the user asks about query syntax,
exactness, or why the phrase changed.

Only mention dynamics operator limits when explicitly asked about exactness or syntax.

