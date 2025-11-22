from src.config import settings


def main():
    print(f"Hello from {settings.app_name}!")
    print(f"Version: {settings.app_version}")
    print(f"Debug mode: {settings.debug}")
    print(f"API will run on: {settings.api_host}:{settings.api_port}")

    # Check if API keys are configured
    if settings.anthropic_api_key:
        print("✓ Anthropic API key configured")
    else:
        print("✗ Anthropic API key not found")

    if settings.openai_api_key:
        print("✓ OpenAI API key configured")
    else:
        print("✗ OpenAI API key not found")


if __name__ == "__main__":
    main()
