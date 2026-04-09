# LinkedIn MCP Server

MCP server for publishing LinkedIn posts via AI assistants (Claude, Cursor, Windsurf, Cline).

## What it does

Exposes two MCP tools:

- `post_to_linkedin` — publish a text post (up to 3000 chars, `PUBLIC` or `CONNECTIONS` visibility)
- `get_linkedin_profile` — retrieve current user profile info

## Setup

### 1. Create LinkedIn App

Go to [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps), create an app, and obtain an Access Token with the following scopes:

- `openid` — to retrieve user ID
- `w_member_social` — to publish posts

### 2. Install dependencies

```bash
pip install -r requirements.txt
pip install -e .
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and add your token
```

Your `.env` file should look like:

```bash
LINKEDIN_ACCESS_TOKEN=your_linkedin_access_token_here
MCP_SECRET_PATH=your_secret_path_here  # optional, recommended for remote deploy
PORT=8000
```

### 4. Run locally

```bash
export LINKEDIN_ACCESS_TOKEN="your_token"
python -m linkedin_mcp.server
```

## Connect to AI Assistants

### Claude Desktop (local)

Add to `claude_desktop_config.json`:

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

### Cursor / Windsurf / Cline (via Railway)

Add a remote MCP server with authorization:

```
URL: https://your-app.railway.app/sse
Headers:
  Authorization: Bearer YOUR_MCP_API_KEY
```

### Any MCP client (HTTP)

```bash
# SSE endpoint (requires Authorization header when MCP_SECRET_PATH is set)
curl -H "Authorization: Bearer YOUR_MCP_API_KEY" \
  https://your-app.railway.app/sse
```

## Deploy on Railway

1. Create a new project on [Railway](https://railway.app)
2. Connect this repository
3. Add environment variables:
   - `LINKEDIN_ACCESS_TOKEN` — your LinkedIn access token
   - `MCP_SECRET_PATH` — secret key to protect the server (generate: `openssl rand -hex 32`)
   - `PORT` — 8000 (Railway sets this automatically)
4. Deploy!

After deployment you will get a URL like: `https://your-app.railway.app`

## Security

The `/sse` endpoint requires an `Authorization: Bearer <MCP_SECRET_PATH>` header when `MCP_SECRET_PATH` is configured. Without it the endpoint is public — suitable for local use only. For any remote deployment, always set `MCP_SECRET_PATH`.

## License

MIT
