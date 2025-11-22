# Data Agent LangGraph

## Overview

A data analysis agent built with LangGraph and LangChain that leverages AI to perform intelligent data operations and analysis.

## Description

This project implements an AI-powered data agent using LangGraph for workflow orchestration and LangChain for language model integration. The agent can interact with data using natural language, perform analysis, and provide insights through a FastAPI backend.

### Key Features

- AI-powered data analysis using LangGraph workflows
- Support for multiple LLM providers (Anthropic Claude, OpenAI)
- Data processing with Pandas and NumPy
- RESTful API built with FastAPI
- Type-safe configuration with Pydantic
- Asynchronous HTTP client support

### Tech Stack

- **LangGraph**: Agent workflow orchestration
- **LangChain**: LLM integration and chains
- **FastAPI**: Modern web framework for APIs
- **Pandas & NumPy**: Data manipulation and analysis
- **Pydantic**: Data validation and settings management
- **Uvicorn**: ASGI server

## Prerequisites

- Python 3.11 or higher
- [UV](https://github.com/astral-sh/uv) package manager (recommended) or pip

## Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd data_agent_langgraph
```

### 2. Install UV (if not already installed)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. Install dependencies

Using UV (recommended):
```bash
uv sync
```

Or using pip:
```bash
pip install -e .
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```bash
# LLM API Keys
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Optional: Configure other settings
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=your_langchain_api_key
```

## Running the Project

### Run the main application

Using UV:
```bash
uv run python main.py
```

Or if activated in virtual environment:
```bash
python main.py
```

### Run the FastAPI server (when implemented)

```bash
uv run uvicorn main:app --reload
```

Or:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

## Development

### Project Structure

```
data_agent_langgraph/
├── main.py              # Main application entry point
├── pyproject.toml       # Project configuration and dependencies
├── uv.lock             # Dependency lock file
├── .env                # Environment variables (create this)
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

### Adding Dependencies

```bash
uv add <package-name>
```

### Running Tests (when implemented)

```bash
uv run pytest
```

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]