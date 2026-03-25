from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App settings
    app_name: str = "Credence AI Backend"
    debug: bool = False

    # Security
    secret_key: str

    # Database
    database_url: str

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    # Frontend
    frontend_url: str

    # Backend URL (for file uploads)
    backend_url: str = ""

    # AI Gateway (for LLM API calls)
    ai_gateway_api_key: str = ""

    # LLM API Keys (provider-specific)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    xai_api_key: str = ""
    openrouter_api_key: str = ""

    # Rate Limiting
    guest_message_limit: int = 20
    regular_user_message_limit: int = 50

    # File Upload Settings
    max_file_size_mb: int = 5
    allowed_image_types: list[str] = ["image/jpeg", "image/png"]

    # Model Configuration
    # Using LangGraph agent with tools for loan assessment
    default_chat_model: str = "anthropic/claude-haiku-4.5"
    default_title_model: str = "anthropic/claude-haiku-4.5"
    default_artifact_model: str = "anthropic/claude-haiku-4.5"

    # Agent Settings
    agent_enabled: bool = True  # Enable/disable LangGraph agent
    agent_model: str = "anthropic/claude-haiku-4.5"  # OpenRouter model ID for agent reasoning
    max_tool_steps: int = 5  # Maximum number of tool execution iterations
    thinking_budget_tokens: int = 10000  # Token budget for extended thinking

    # Redis (optional, for future use)
    redis_url: str = ""

    # RAG & Embeddings (for lending knowledge base)
    embedding_model: str = "perplexity/pplx-embed-v1-0.6b"
    embedding_dimensions: int = 1024
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 100
    rag_retrieval_k: int = 5

    # MCP (Model Context Protocol) Settings
    mcp_supabase_url: str = ""  # Supabase MCP server SSE endpoint (e.g., "http://localhost:8000/sse")
    mcp_supabase_transport: str = "sse"  # Transport type: "sse" or "stdio"

    # Database connection details (parsed from database_url or set individually)
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "credence"
    database_user: str = "credence"
    database_password: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
