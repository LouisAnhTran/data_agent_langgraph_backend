"""Main entry point for Data Agent LangGraph application"""

import uvicorn
from src.config import settings
from src.utils.logger import setup_logging

# Setup logging
setup_logging(
    log_level=settings.log_level,
    log_to_file=settings.log_to_file,
    log_dir=settings.log_dir
)


def main():
    """Run the FastAPI application"""
    print(f"Starting {settings.app_name}...")
    print(f"Version: {settings.app_version}")
    print(f"Debug mode: {settings.debug}")
    print(f"API will run on: http://{settings.api_host}:{settings.api_port}")
    print(f"Docs available at: http://{settings.api_host}:{settings.api_port}/docs")

    # Check if API keys are configured
    if settings.anthropic_api_key:
        print("✓ Anthropic API key configured")
    else:
        print("✗ Anthropic API key not found")

    if settings.openai_api_key:
        print("✓ OpenAI API key configured")
    else:
        print("✗ OpenAI API key not found")

    print("\nStarting server...\n")

    # Run the FastAPI application
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
