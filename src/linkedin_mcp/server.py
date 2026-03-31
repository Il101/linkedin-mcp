"""LinkedIn MCP Server"""

import os
import asyncio
import secrets
import hashlib
import time
import json
from urllib.parse import urlencode, parse_qs
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent, Prompt, PromptMessage
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response, RedirectResponse, JSONResponse

from .linkedin import LinkedInClient


server = Server("linkedin-mcp")

# OAuth configuration (set in environment)
OAUTH_CLIENT_ID = os.getenv("OAUTH_CLIENT_ID", "linkedin-mcp-client")
OAUTH_CLIENT_SECRET = os.getenv("OAUTH_CLIENT_SECRET")

# Store for authorization codes and tokens (in production use Redis/DB)
auth_codes = {}  # code -> {client_id, expires}
access_tokens = {}  # token -> {client_id, expires}


def generate_token():
    """Generate a secure random token"""
    return secrets.token_urlsafe(32)


def verify_token(request) -> bool:
    """Verify OAuth access token"""
    if not OAUTH_CLIENT_SECRET:
        return True  # No auth if not configured
    
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        token_data = access_tokens.get(token)
        if token_data and token_data["expires"] > time.time():
            return True
    return False


@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    """List available prompts for AI assistants"""
    return [
        Prompt(
            name="linkedin_post_creator",
            description="Guide for creating engaging LinkedIn posts",
            arguments=[
                {
                    "name": "topic",
                    "description": "The topic or subject of the post",
                    "required": False
                }
            ]
        ),
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict) -> PromptMessage:
    """Get prompt content"""
    if name == "linkedin_post_creator":
        topic = arguments.get("topic", "your expertise")
        return PromptMessage(
            role="user",
            content={
                "type": "text",
                "text": f"""You are helping create a LinkedIn post about {topic}.

Best practices for LinkedIn posts:
1. Start with a hook - grab attention in the first line
2. Keep it concise - 150-300 words is optimal
3. Use line breaks for readability
4. Add relevant emojis sparingly (1-3 per post)
5. Include a call-to-action if appropriate
6. Use hashtags (2-5 relevant ones)
7. Professional but conversational tone

Post structure:
- Hook (1-2 lines)
- Main content (value, story, or insight)
- Conclusion or CTA
- Hashtags

When ready, use the post_to_linkedin tool to publish."""
            }
        )
    raise ValueError(f"Unknown prompt: {name}")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="post_to_linkedin",
            description="Publish a text post to LinkedIn. Use this to share professional content, insights, or updates with your network.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The content of the post (max 3000 characters). Can include emojis, line breaks, and hashtags."
                    },
                    "visibility": {
                        "type": "string",
                        "enum": ["PUBLIC", "CONNECTIONS"],
                        "default": "PUBLIC",
                        "description": "Post visibility: PUBLIC (anyone on LinkedIn) or CONNECTIONS (only your connections)"
                    }
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="get_linkedin_profile",
            description="Get the current user's LinkedIn profile information (name, email, user ID). Useful for verifying authentication before posting.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    
    try:
        client = LinkedInClient()
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    if name == "post_to_linkedin":
        text = arguments.get("text", "")
        visibility = arguments.get("visibility", "PUBLIC")
        
        if not text:
            return [TextContent(type="text", text="Error: Post text is required")]
        
        if len(text) > 3000:
            return [TextContent(type="text", text="Error: Post text exceeds 3000 characters")]
        
        try:
            result = await client.create_post(text, visibility)
            return [TextContent(
                type="text", 
                text=f"✅ Post published successfully!\nPost ID: {result['id']}"
            )]
        except Exception as e:
            return [TextContent(type="text", text=f"Error posting to LinkedIn: {str(e)}")]
    
    elif name == "get_linkedin_profile":
        try:
            profile = await client.get_profile()
            return [TextContent(
                type="text",
                text=f"LinkedIn Profile:\n"
                     f"Name: {profile.get('name', 'N/A')}\n"
                     f"Email: {profile.get('email', 'N/A')}\n"
                     f"ID: {profile.get('sub', 'N/A')}"
            )]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting profile: {str(e)}")]
    
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def handle_sse(request):
    """Handle SSE endpoint for remote connections"""
    # Check OAuth token
    if not verify_token(request):
        return Response("Unauthorized", status_code=401)
    
    transport = SseServerTransport("/messages")
    
    async with transport.connect_sse(
        request.scope,
        request.receive,
        request._send,
    ) as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )
    
    return Response()


async def handle_messages(request):
    """Handle messages endpoint"""
    if not verify_token(request):
        return Response("Unauthorized", status_code=401)
    return Response()


async def handle_health(request):
    """Health check endpoint (no auth required)"""
    return Response("LinkedIn MCP Server is running")


async def handle_oauth_authorize(request):
    """OAuth 2.0 Authorization endpoint with PKCE support"""
    params = dict(request.query_params)
    client_id = params.get("client_id")
    redirect_uri = params.get("redirect_uri")
    response_type = params.get("response_type")
    state = params.get("state", "")
    code_challenge = params.get("code_challenge")
    code_challenge_method = params.get("code_challenge_method")
    
    # Validate client_id
    if client_id != OAUTH_CLIENT_ID:
        return Response("Invalid client_id", status_code=400)
    
    if response_type != "code":
        return Response("Only response_type=code is supported", status_code=400)
    
    # Generate authorization code
    code = generate_token()
    auth_codes[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "expires": time.time() + 600  # 10 minutes
    }
    
    # Redirect back with code
    redirect_params = {"code": code}
    if state:
        redirect_params["state"] = state
    
    redirect_url = f"{redirect_uri}?{urlencode(redirect_params)}"
    return RedirectResponse(redirect_url)


def verify_code_challenge(code_verifier: str, code_challenge: str, method: str) -> bool:
    """Verify PKCE code challenge"""
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode()).digest()
        computed = secrets.token_urlsafe(0).join(
            chr(b) for b in digest
        )
        # Base64url encode
        import base64
        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return secrets.compare_digest(computed, code_challenge)
    elif method == "plain":
        return secrets.compare_digest(code_verifier, code_challenge)
    return False


async def handle_oauth_token(request):
    """OAuth 2.0 Token endpoint with PKCE support"""
    # Parse form data
    form = await request.form()
    grant_type = form.get("grant_type")
    code = form.get("code")
    client_id = form.get("client_id")
    client_secret = form.get("client_secret")
    code_verifier = form.get("code_verifier")
    
    # Validate grant type
    if grant_type != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    
    # Validate client_id
    if client_id != OAUTH_CLIENT_ID:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    
    # Validate authorization code
    code_data = auth_codes.get(code)
    if not code_data or code_data["expires"] < time.time():
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    
    if code_data["client_id"] != client_id:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    
    # Verify PKCE if code_challenge was provided during authorization
    if code_data.get("code_challenge"):
        if not code_verifier:
            return JSONResponse({"error": "invalid_grant", "error_description": "code_verifier required"}, status_code=400)
        if not verify_code_challenge(code_verifier, code_data["code_challenge"], code_data.get("code_challenge_method", "plain")):
            return JSONResponse({"error": "invalid_grant", "error_description": "code_verifier mismatch"}, status_code=400)
    elif OAUTH_CLIENT_SECRET and client_secret != OAUTH_CLIENT_SECRET:
        # If no PKCE, require client_secret
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    
    # Delete used code
    del auth_codes[code]
    
    # Generate access token
    access_token = generate_token()
    expires_in = 86400  # 24 hours
    access_tokens[access_token] = {
        "client_id": client_id,
        "expires": time.time() + expires_in
    }
    
    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in
    })


async def handle_oauth_metadata(request):
    """OAuth 2.0 Authorization Server Metadata"""
    # Use HTTPS in production
    base_url = str(request.base_url).rstrip("/")
    if os.getenv("RAILWAY_ENVIRONMENT"):
        base_url = base_url.replace("http://", "https://")
    
    return JSONResponse({
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"]
    })


async def handle_protected_resource_metadata(request):
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)"""
    base_url = str(request.base_url).rstrip("/")
    if os.getenv("RAILWAY_ENVIRONMENT"):
        base_url = base_url.replace("http://", "https://")
    
    return JSONResponse({
        "resource": base_url,
        "authorization_servers": [base_url],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["claudeai"]
    })


# Starlette app for HTTP/SSE mode
app = Starlette(
    routes=[
        # MCP endpoints
        Route("/sse", endpoint=handle_sse),
        Route("/messages", endpoint=handle_messages, methods=["POST"]),
        
        # OAuth 2.0 endpoints
        Route("/oauth/authorize", endpoint=handle_oauth_authorize),
        Route("/oauth/token", endpoint=handle_oauth_token, methods=["POST"]),
        Route("/.well-known/oauth-authorization-server", endpoint=handle_oauth_metadata),
        Route("/.well-known/oauth-protected-resource", endpoint=handle_protected_resource_metadata),
        
        # Health check
        Route("/", endpoint=handle_health),
        Route("/health", endpoint=handle_health),
    ]
)


def main():
    """Run the MCP server"""
    import sys
    
    # Check if running in HTTP mode (for Railway)
    if os.getenv("RAILWAY_ENVIRONMENT") or "--http" in sys.argv:
        import uvicorn
        port = int(os.getenv("PORT", 8000))
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Run in stdio mode (for local Claude Desktop)
        asyncio.run(run_stdio_server())


async def run_stdio_server():
    """Run the stdio server for local connections"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    main()
