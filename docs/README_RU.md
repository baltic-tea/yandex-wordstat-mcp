🇬🇧 [English](../README.md) | 🇷🇺 [Русский](./README_RU.md)

# MCP-сервер Yandex Wordstat

MCP-сервер для Yandex Wordstat API v2, построенный на `FastMCP`.

## Возможности

- MCP-инструменты для методов Yandex Wordstat API v2:
    - [getTop](https://aistudio.yandex.ru/docs/ru/search-api/api-ref/Wordstat/getTop.html)
    - [getDynamics](https://aistudio.yandex.ru/docs/ru/search-api/api-ref/Wordstat/getDynamics.html)
    - [getRegionsDistribution](https://aistudio.yandex.ru/docs/ru/search-api/api-ref/Wordstat/getRegionsDistribution.html)
    - [getRegionsTree](https://aistudio.yandex.ru/docs/ru/search-api/api-ref/Wordstat/getRegionsTree.html)
- Аутентификация по API-ключу или IAM-токену.
- Пакетная обработка фраз с пагинацией.
- Типизированные модели запросов.
- Локальный кеш компактного справочника регионов Wordstat в `.saved/regions_tree.json`.
- Быстрый поиск регионов по названию через `find_regions`.
- Операторный сборщик фраз для точных форм, стоп-слов, порядка слов и альтернатив.
- AI-first алиасы для типовых задач по ключевым словам, динамике и регионам.
- Краткая `<api>method=...; endpoint=...</api>` metadata в описаниях публичных tools.
- Повторные попытки при временных транспортных ошибках и ответах `429/5xx`.

## Системные требования

- Python `3.11+`
- Рекомендуется `uv`, также поддерживается `pip`.
- Доступ к Yandex Cloud Wordstat API.

## Установка

Для обычной настройки MCP-клиента запускайте сервер прямо из Git через `uvx`:

```bash
uvx --from git+https://github.com/baltic-tea/yandex-wordstat-mcp.git wordstat-mcp
```

`uvx` создает изолированное окружение и запускает console script
`wordstat-mcp`, опубликованный пакетом.

## Установка для разработки

1. Клонируйте репозиторий:

```bash
git clone https://github.com/baltic-tea/yandex-wordstat-mcp.git
cd yandex-wordstat-mcp
```

2. Установите зависимости через `uv` или `pip`.

### Через `uv`

```bash
uv sync --all-groups
```

### Через `pip`

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

## Конфигурация

Скопируйте `.env.example` в `.env` и заполните учетные данные.

`WORDSTAT_FOLDER_ID` обязателен для каждого API-запроса. Укажите либо
`WORDSTAT_API_KEY`, либо `WORDSTAT_IAM_TOKEN`; если указаны оба значения, будет
использован `WORDSTAT_IAM_TOKEN`.

## Запуск сервера

Console entrypoint:

```bash
wordstat-mcp
```

Сервер использует stdio-транспорт через `FastMCP`.

## Docker / Podman

Соберите image из корня репозитория:

```bash
docker build -t yandex-wordstat-mcp:latest .
```

Запустите сервер через stdio:

```bash
docker run --rm -i \
  -e WORDSTAT_FOLDER_ID=your-folder-id \
  -e WORDSTAT_API_KEY=your-api-key \
  yandex-wordstat-mcp:latest
```

Используйте `-e WORDSTAT_IAM_TOKEN=your-iam-token` вместо
`-e WORDSTAT_API_KEY=your-api-key`, если аутентифицируетесь через IAM token.
Добавьте `-v wordstat-mcp-cache:/app/.saved`, если нужно сохранять Wordstat
regions cache между запусками container.

Для Podman используйте те же команды, заменив `docker` на `podman`:

```bash
podman build -t yandex-wordstat-mcp:latest .
podman run --rm -i \
  -e WORDSTAT_FOLDER_ID=your-folder-id \
  -e WORDSTAT_API_KEY=your-api-key \
  yandex-wordstat-mcp:latest
```

Пример MCP client config для локального Docker image:

```json
{
  "mcpServers": {
    "yandex-wordstat": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "-e",
        "WORDSTAT_FOLDER_ID=your-folder-id",
        "-e",
        "WORDSTAT_API_KEY=your-api-key",
        "yandex-wordstat-mcp:latest"
      ]
    }
  }
}
```

## Доступные инструменты

### `getTop`

Возвращает популярные и связанные фразы для одной или нескольких входных фраз.

### `build_wordstat_phrase`

Собирает и валидирует `phrase` для Wordstat из естественно-языкового запроса
на русском и необязательных подсказок о намерении. Используйте перед `getTop`,
`getDynamics` или `getRegionsDistribution`, когда пользователь просит точную
фразу, фиксированный порядок слов, обязательные стоп-слова, фиксированные формы
слов или альтернативы.

### `getDynamics`

Возвращает динамику спроса для одной или нескольких фраз за диапазон дат.

`fromDate` обязателен и должен быть временной меткой RFC3339, например
`2026-01-01T00:00:00Z`. `toDate` необязателен; если он не передан, сервер
использует текущую метку UTC. Модели запроса нормализуют диапазон к границам
периода Wordstat: `fromDate` переносится на начало дня, а `toDate` после
выравнивания по месяцу, неделе или дню переносится на конец дня
(`23:59:59.999999Z`).

Динамика Wordstat поддерживает только оператор `+`. Сервер отклоняет фразы
для `getDynamics`, если они содержат `!`, кавычки, `[]`, `()` или `|`.

### `getRegionsDistribution`

Возвращает распределение по регионам для одной или нескольких фраз.

### `getRegionsTree`

Возвращает компактный индекс регионов с названиями в нижнем регистре и ID.
Локальный кеш хранится в `.saved/regions_tree.json` в таком формате:

```json
{
  "by_name": {
    "зеленоград": ["216"],
    "троицк": ["20674"]
  },
  "by_id": {
    "216": {
      "name": "Зеленоград",
      "path": ["Россия", "Москва и Московская область", "Зеленоград"]
    }
  }
}
```

`by_name` всегда сопоставляет нормализованное lowercase-название со списком
строковых ID, потому что одно видимое название региона может соответствовать
нескольким ID Wordstat.

Если файл `.saved/regions_tree.json` существует, инструмент читает его локально
и не вызывает внешний API. Если файла нет, инструмент получает дерево регионов
из API, преобразует его в компактный индекс и сохраняет индекс в
`.saved/regions_tree.json`.

### `find_regions`

Ищет ID регионов: сначала прямым lowercase-вхождением, затем substring fallback.
Используйте перед передачей пользовательских названий городов или регионов в
параметр `regions` у `getTop` или `getDynamics`.

`find_regions` читает кешированный индекс `getRegionsTree`, поэтому повторные
поиски локальные после первого заполнения кеша. Для большого списка городов
агент может один раз вызвать `get_region_index` и брать точные совпадения из
`by_name`; отдельный batch-инструмент обычно не окупает расширение API.

### `update_regions_tree`

Обновляет `.saved/regions_tree.json` из API, даже если кешированный справочник
уже существует.

### AI-first алиасы

Эти инструменты дают то же поведение через task-oriented названия:

- `find_keyword_queries` делегирует в `getTop`.
- `get_query_demand_trends` делегирует в `getDynamics`.
- `compare_query_demand_by_region` делегирует в `getRegionsDistribution`.
- `get_region_index` делегирует в `getRegionsTree`.

### `wordstat_env_health`

Возвращает состояние локальной конфигурации без вызова внешнего API.

## Prompt и Resource

Сервер публикует MCP-инструкции для агентов, которым нужно собирать Wordstat
фразы из естественного языка:

- Resource: `wordstat://operators/agent-guide`
- Prompt: `wordstat_phrase_builder`
- Tool: `build_wordstat_phrase`

MCP prompts и resources являются рекомендательным контекстом. Сервер может
опубликовать их и описать, когда их использовать, но MCP-клиент или LLM сам
решает, загружать и соблюдать ли их. Critical constraints enforced на стороне
tools: `getDynamics` валидирует операторы на стороне сервера, а
`build_wordstat_phrase` возвращает предупреждения, когда вынужден удалить
неподдерживаемые операторы.

## Интеграция

Примеры ниже используют запуск через `uvx` + Git:

```json
{
  "mcpServers": {
    "yandex-wordstat": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/baltic-tea/yandex-wordstat-mcp.git",
        "wordstat-mcp"
      ],
      "env": {
        "WORDSTAT_FOLDER_ID": "your-folder-id",
        "WORDSTAT_API_KEY": "your-api-key"
      }
    }
  }
}
```

Используйте `"WORDSTAT_IAM_TOKEN": "your-iam-token"` вместо
`"WORDSTAT_API_KEY": "your-api-key"`, если аутентифицируетесь через IAM token.

Для разработки из клона используйте `wordstat-mcp` из активированного
виртуального окружения или `uv run wordstat-mcp` внутри репозитория.

Клиенты, которые поддерживают этот JSON-формат `mcpServers` напрямую или с минимальными изменениями пути: Claude Desktop, Claude Code, Windsurf, Qwen Codem, Kilo Code, Trae.

Клиенты, которые поддерживают MCP, но используют другой формат настройки: Codex, OpenCode.

### Claude Code

Рекомендуемая настройка на уровне проекта:

```bash
claude mcp add yandex-wordstat --scope project --transport stdio \
  --env WORDSTAT_FOLDER_ID=your-folder-id \
  --env WORDSTAT_API_KEY=your-api-key \
  -- uvx --from git+https://github.com/baltic-tea/yandex-wordstat-mcp.git wordstat-mcp
```

Используйте `--env WORDSTAT_IAM_TOKEN=your-iam-token` вместо
`--env WORDSTAT_API_KEY=your-api-key`, если аутентифицируетесь через IAM token.

Проверка:

```bash
claude mcp list
```

В Claude Code выполните `/mcp`, чтобы проверить состояние сервера и при необходимости
аутентифицировать удаленные MCP-серверы.

Если нужен проектный конфиг в репозитории, создайте `.mcp.json` в корне проекта.

Claude Code также поддерживает импорт JSON-описания сервера:

```bash
claude mcp add-json yandex-wordstat '{"type":"stdio","command":"uvx","args":["--from","git+https://github.com/baltic-tea/yandex-wordstat-mcp.git","wordstat-mcp"],"env":{"WORDSTAT_FOLDER_ID":"your-folder-id","WORDSTAT_API_KEY":"your-api-key"}}'
```

Для IAM-token authentication замените `WORDSTAT_API_KEY` на
`WORDSTAT_IAM_TOKEN` в JSON object `env`.

### Codex

Codex поддерживает MCP в CLI и расширении VS Code IDE. Он не использует объект
`mcpServers` напрямую, поэтому настройте сервер через CLI или TOML-конфиг.

Пример CLI:

```bash
codex mcp add yandex_wordstat_mcp --command uvx -- --from git+https://github.com/baltic-tea/yandex-wordstat-mcp.git wordstat-mcp
codex mcp list
```

Если удобнее редактировать конфиг напрямую, измените файл `~/.codex/config.toml`:

```toml
[mcp_servers.yandex_wordstat_mcp]
command = "uvx"
args = ["--from", "git+https://github.com/baltic-tea/yandex-wordstat-mcp.git", "wordstat-mcp"]

[mcp_servers.yandex_wordstat_mcp.env]
WORDSTAT_FOLDER_ID = "your-folder-id"
WORDSTAT_API_KEY = "your-api-key"
```

Для IAM-token authentication замените `WORDSTAT_API_KEY` на
`WORDSTAT_IAM_TOKEN`.

Проверка:

```bash
codex mcp list
```

## Лицензия

Проект распространяется по лицензии GNU General Public License v3.0. См. [LICENSE](../LICENSE).

## Авторы

- [baltic_tea](https://github.com/baltic-tea)
