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
3. Добавь переменные окружения:
   - `LINKEDIN_ACCESS_TOKEN` — твой токен
   - `PORT` — 8000 (Railway добавит автоматически)
4. Deploy!

После деплоя получишь URL вида: `https://your-app.railway.app`

## Подключение к AI-ассистентам

### Claude Desktop (локально)

Добавь в `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "linkedin": {
      "command": "python3",
      "args": ["-m", "linkedin_mcp.server"],
      "env": {
        "LINKEDIN_ACCESS_TOKEN": "your_token"
      }
    }
  }
}
```

### Cursor / Windsurf / Cline (через Railway)

Добавь удаленный MCP сервер:

```
URL: https://your-app.railway.app/sse
```

### Любой MCP клиент (HTTP)

```bash
# SSE endpoint
https://your-app.railway.app/sse

# Messages endpoint  
https://your-app.railway.app/messages
```

## LinkedIn API Scopes

Для работы сервера нужны следующие разрешения:
- `openid` — для получения user ID
- `w_member_social` — для публикации постов

## Лицензия

MIT
