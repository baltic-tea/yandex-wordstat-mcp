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
- Локальный кеш дерева регионов Wordstat в `.saved/regions_tree.json`.
- Повторные попытки при временных транспортных ошибках и ответах `429/5xx`.

## Системные требования

- Python `3.11+`
- Рекомендуется `uv`, также поддерживается `pip`.
- Доступ к Yandex Cloud Wordstat API.

## Установка

Сначала клонируйте репозиторий:

```bash
git clone https://github.com/baltic-tea/yandex-wordstat-mcp.git
cd yandex-wordstat-mcp
```

### Через `uv`

```bash
uv sync
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

`WORDSTAT_FOLDER_ID` обязателен для каждого API-запроса. Если вместе с `WORDSTAT_API_KEY` указан `WORDSTAT_IAM_TOKEN`, будет использован `WORDSTAT_IAM_TOKEN`.

## Сборка из исходников

Шаги сборки:

1. Установите зависимости через `uv sync --all-groups` или `pip install -e .`.
2. Если используете `pip`, убедитесь, что виртуальное окружение активировано.
3. Запустите команду сборки ниже.

```bash
uv build
```

## Запуск сервера

Точка входа модуля:

```bash
python -m wordstat_mcp
```

Сервер использует stdio-транспорт через `FastMCP`.

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

`fromDate` и `toDate` должны быть временными метками RFC3339, например
`2026-01-01T00:00:00Z`.

Динамика Wordstat поддерживает только оператор `+`. Сервер отклоняет фразы
для `getDynamics`, если они содержат `!`, кавычки, `[]`, `()` или `|`.

### `getRegionsDistribution`

Возвращает распределение по регионам для одной или нескольких фраз.

### `getRegionsTree`

Возвращает полное дерево регионов, поддерживаемое API Яндекса.

Если файл `.saved/regions_tree.json` существует, инструмент читает его локально
и не вызывает внешний API. Если файла нет, инструмент получает дерево из API и
сохраняет его в `.saved/regions_tree.json`.

### `update_regions_tree`

Обновляет `.saved/regions_tree.json` из API, даже если кешированный файл уже существует.

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
решает, загружать и соблюдать ли их. Критичные ограничения enforced на стороне
tools: `getDynamics` валидирует операторы на сервере, а `build_wordstat_phrase`
возвращает предупреждения, когда вынужден удалить неподдерживаемые операторы.

## Интеграция

Примеры ниже используют локальный запуск через stdio:

```json
{
  "mcpServers": {
    "yandex-wordstat": {
      "command": "python",
      "args": ["-m", "wordstat_mcp"],
      "cwd": "/absolute/path/to/yandex-wordstat-mcp",
      "env": {
        "WORDSTAT_FOLDER_ID": "your-folder-id",
        "WORDSTAT_API_KEY": "your-api-key"
      }
    }
  }
}
```

При необходимости замените `python` на явный путь к интерпретатору.

Клиенты, которые поддерживают этот JSON-формат `mcpServers` напрямую или с минимальными изменениями пути: Claude Desktop, Claude Code, Windsurf, Qwen Codem, Kilo Code, Trae.

Клиенты, которые поддерживают MCP, но используют другой формат настройки: Codex, OpenCode.

### Claude Code

Рекомендуемая настройка на уровне проекта:

```bash
claude mcp add yandex-wordstat --scope project --transport stdio \
  --env WORDSTAT_FOLDER_ID=your-folder-id \
  --env WORDSTAT_API_KEY=your-api-key \
  -- python -m wordstat_mcp
```

Проверка:

```bash
claude mcp list
```

В Claude Code выполните `/mcp`, чтобы проверить состояние сервера и при необходимости
аутентифицировать удаленные MCP-серверы.

Если нужен проектный конфиг в репозитории, создайте `.mcp.json` в корне проекта.

Claude Code также поддерживает импорт JSON-описания сервера:

```bash
claude mcp add-json yandex-wordstat '{"type":"stdio","command":"python","args":["-m","wordstat_mcp"],"cwd":"/absolute/path/to/yandex-wordstat-mcp","env":{"WORDSTAT_FOLDER_ID":"your-folder-id","WORDSTAT_API_KEY":"your-api-key"}}'
```

### Codex

Codex поддерживает MCP в CLI и расширении VS Code IDE. Он не использует объект
`mcpServers` напрямую, поэтому настройте сервер через CLI или TOML-конфиг.

Пример CLI:

```bash
codex mcp add yandex_wordstat_mcp --command python -- -m wordstat_mcp
codex mcp list
```

Если удобнее редактировать конфиг напрямую, измените файл `~/.codex/config.toml`:

```toml
[mcp_servers.yandex_wordstat_mcp]
command = "python"
args = ["-m", "wordstat_mcp"]
cwd = "/absolute/path/to/yandex-wordstat-mcp"

[mcp_servers.yandex_wordstat_mcp.env]
WORDSTAT_FOLDER_ID = "your-folder-id"
WORDSTAT_API_KEY = "your-api-key"
```

Проверка:

```bash
codex mcp list
```

## Лицензия

Проект распространяется по лицензии GNU General Public License v3.0. См. [LICENSE](../LICENSE).

## Авторы

- [baltic_tea](https://github.com/baltic-tea)
