# LinkedIn MCP Server

MCP сервер для публикации постов в LinkedIn через AI-ассистентов.

## Установка

```bash
pip install -r requirements.txt
pip install -e .
```

## Настройка

1. Создай приложение в [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps)
2. Получи Access Token с правами `w_member_social` и `openid`
3. Создай `.env` файл:

```bash
cp .env.example .env
# Отредактируй .env и добавь свой токен
```

## Локальный запуск

```bash
export LINKEDIN_ACCESS_TOKEN="your_token"
python -m linkedin_mcp.server
```

## Инструменты (Tools)

### `post_to_linkedin`
Публикует текстовый пост в LinkedIn.

**Параметры:**
- `text` (string, required) — текст поста (до 3000 символов)
- `visibility` (string, optional) — `PUBLIC` или `CONNECTIONS` (по умолчанию `PUBLIC`)

### `get_linkedin_profile`
Получает информацию о профиле текущего пользователя.

## Деплой на Railway

1. Создай новый проект на [Railway](https://railway.app)
2. Подключи этот репозиторий
3. Добавь переменную окружения `LINKEDIN_ACCESS_TOKEN`
4. Deploy!

## Использование с Claude Desktop

Добавь в `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "linkedin": {
      "command": "python",
      "args": ["-m", "linkedin_mcp.server"],
      "env": {
        "LINKEDIN_ACCESS_TOKEN": "your_token"
      }
    }
  }
}
```

## Использование с Cursor

Добавь в настройки MCP серверов URL твоего Railway деплоя.

## LinkedIn API Scopes

Для работы сервера нужны следующие разрешения:
- `openid` — для получения user ID
- `w_member_social` — для публикации постов

## Лицензия

MIT
