"""LinkedIn MCP Server"""

import os
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent, Prompt, PromptMessage
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import Response

from .linkedin import LinkedInClient


server = Server("linkedin-mcp")

# Secret path for SSE endpoint (set in environment)
SECRET_PATH = os.getenv("MCP_SECRET_PATH", "")


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


# SSE transport instance (reused for message routing)
sse_transport = None


async def handle_sse(request):
    """Handle SSE endpoint for MCP connections"""
    global sse_transport
    
    # Create transport with message path
    sse_transport = SseServerTransport("/messages")
    
    async with sse_transport.connect_sse(
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
    """Handle POST messages from MCP client"""
    global sse_transport
    
    if sse_transport is None:
        return Response("No active SSE connection", status_code=400)
    
    # Forward to SSE transport
    return await sse_transport.handle_post_message(
        request.scope,
        request.receive,
        request._send,
    )


async def handle_health(request):
    """Health check endpoint"""
    return Response("LinkedIn MCP Server is running")


def create_app():
    """Create the Starlette app with routes"""
    routes = [
        Route("/", endpoint=handle_health),
        Route("/health", endpoint=handle_health),
    ]
    
    # If secret path is set, use it for SSE endpoint
    if SECRET_PATH:
        sse_path = f"/sse/{SECRET_PATH}"
        messages_path = f"/messages/{SECRET_PATH}"
    else:
        sse_path = "/sse"
        messages_path = "/messages"
    
    routes.extend([
        Route(sse_path, endpoint=handle_sse),
        Route(messages_path, endpoint=handle_messages, methods=["POST"]),
    ])
    
    return Starlette(routes=routes)


app = create_app()


def main():
    """Run the MCP server"""
    import sys
    
    # Check if running in HTTP mode (for Railway)
    if os.getenv("RAILWAY_ENVIRONMENT") or "--http" in sys.argv:
        import uvicorn
        port = int(os.getenv("PORT", 8000))
        
        if SECRET_PATH:
            print(f"🔐 SSE endpoint: /sse/{SECRET_PATH}")
        else:
            print("⚠️  No MCP_SECRET_PATH set - endpoint is public at /sse")
        
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
