# LinkedIn MCP Server

MCP server for publishing, inspecting, and deleting LinkedIn posts via AI assistants (Claude, Cursor, Windsurf, Cline).

Uses the **Streamable HTTP** transport (MCP spec 2025-03-26) for remote deployments and **stdio** for local use with Claude Desktop.

## Tools

| Tool | What it does | Side effects |
|---|---|---|
| `post_to_linkedin` | Publish a text post (up to 3000 chars, PUBLIC or CONNECTIONS visibility) | Writes |
| `get_linkedin_profile` | Get current user's name, email, and LinkedIn ID | Read-only |
| `delete_linkedin_post` | Delete a post by URN — **irreversible** | Destructive |

## Prompt

`linkedin_post_creator` — a guided prompt for composing LinkedIn posts. Accepts an optional `topic` argument.

## Setup

### 1. Create a LinkedIn App

Go to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps), create an app, and add these OAuth 2.0 scopes:

- `openid` — retrieve user ID
- `profile` — retrieve user name
- `w_member_social` — publish and delete posts

### 2. Install

```bash
pip install -r requirements.txt
pip install -e .
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in LINKEDIN_ACCESS_TOKEN and MCP_API_KEY
```

### 4. Get a LinkedIn access token

```bash
# Set your OAuth app credentials in the environment first:
export LINKEDIN_CLIENT_ID="your_client_id"
export LINKEDIN_CLIENT_SECRET="your_client_secret"

python get_token.py
# Follow the browser prompt — your access token will be printed
# Note: LinkedIn access tokens expire after ~60 days; rerun this script to renew
```

## Connect to AI Assistants

### Claude Desktop (stdio — local)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "linkedin": {
      "command": "linkedin-mcp",
      "env": {
        "LINKEDIN_ACCESS_TOKEN": "your_token"
      }
    }
  }
}
```

### Claude Code / Cursor / Windsurf (remote via Railway)

Add a remote MCP server:

```
URL: https://your-app.railway.app/mcp
Authorization: Bearer YOUR_MCP_API_KEY
```

## Deploy on Railway

1. Create a new project on [Railway](https://railway.app) and connect this repository.
2. Set these environment variables:
   - `LINKEDIN_ACCESS_TOKEN` — your LinkedIn access token
   - `MCP_API_KEY` — a secret key protecting the `/mcp` endpoint (`openssl rand -hex 32`)
   - `PORT` — Railway sets this automatically
3. Deploy. Your server will be at `https://your-app.railway.app`.

## Security

- All requests to `/mcp` require `Authorization: Bearer <MCP_API_KEY>` when `MCP_API_KEY` is set.
- `/` and `/health` are public (no token needed).
- If `MCP_API_KEY` is not set, the server runs without auth — suitable for local use only.
- Never commit your `.env` file. It is in `.gitignore`.

## License

MIT
