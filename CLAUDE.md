# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.


## Workflow
- Always prompt for confirmation before making any file changes. Never modify, create, or delete files without explicit approval.


## Project Overview

Data Agent LangGraph is an AI-powered data analysis agent built with LangGraph and LangChain. The agent processes natural language queries to search and analyze documents in a document management system, using LLM-driven intent classification and structured query building.

## Development Commands

### Environment Setup
```bash
# Install dependencies using UV (recommended)
uv sync

# Or using pip
pip install -e .
```

### Running the Application
```bash
# Run main application
uv run python main.py

# Run FastAPI server (when implemented)
uv run uvicorn main:app --reload

# With custom host/port
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Working with Notebooks
- Development and testing notebooks are located in `src/graphs/notebooks/`
- Main graph notebook: `src/graphs/notebooks/data_agent_graph.ipynb`
- Subgraph notebooks: `src/graphs/notebooks/queue_processing_graph.ipynb`

### Adding Dependencies
```bash
uv add <package-name>
```

## Architecture

### LangGraph Workflow Structure

The codebase uses a multi-level graph architecture with a main graph that orchestrates subgraphs for specific processing tasks.

#### Main Graph Flow
1. **Intent Classification** - Classifies user queries into: search, document_accuracy, document_counter, document_processing_time, or others
2. **Search Attributes Extraction** - For search intent, extracts attributes: document_model, queue, or date
3. **Router for Processing Attributes** - Routes to appropriate subgraphs based on detected attributes
4. **Subgraph Processing** - Delegates to specialized subgraphs (e.g., queue processing)

#### Queue Processing Subgraph
Located in `src/graphs/sub_graphs/queue_processing_graph.py`, this subgraph:
1. Fetches available queues from GraphQL API
2. Extracts queue names from user query using LLM with fuzzy matching
3. Maps extracted queue names to IDs
4. Updates the search payload with queue information
5. Uses human-in-the-loop via `interrupt_before=["user_refine_search_query"]` to handle ambiguous queries

### State Management

**OverallState** (main graph state):
- `messages`: Conversation history using `add_messages` reducer
- `intent`: Classified user intent
- `search_attributes`: List of detected search attributes
- `search_payload`: Structured search parameters using custom `reduce_search_payload` reducer

**QueueOverallState** (queue subgraph state):
- Inherits channels from main graph
- Adds node-specific channels: `map_queues_to_ids`, `map_extracted_queue_to_ids`

**SearchPayload TypedDict**:
- `uploaded_at`: Date range
- `queues`: Queue name to ID mapping
- `others`: Document fields and values

### Custom Reducers

`reduce_search_payload` in `src/graphs/custom_reducers/reduce_search_payload.py`:
- Merges search payload updates from different nodes
- Handles None values by treating them as empty dicts
- Uses dict update to combine left and right state

### Prompts Organization

All LLM prompts are centralized in `src/graphs/prompts/`:
- `intent_classification.py` - INTENT_CLASSIFICATION_PROMPT
- `search_attributes_extraction.py` - SEARCH_ATTRIBUTES_EXTRACTION_PROMPT
- `extract_queues_from_search_query.py` - QUEUES_NAME_EXTRACTION_FROM_QUERY_PROMPT

Each prompt includes detailed instructions, examples, and edge cases.

### Configuration

Settings are managed via Pydantic Settings in `src/config.py`:
- Loads from `.env` file (use `.env.example` as template)
- Required API keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- Default LLM: `gpt-4o` with temperature `0.7`
- Optional LangChain tracing configuration

### Checkpointing and Memory

The graph uses `MemorySaver` checkpointer for:
- Maintaining conversation state across interactions
- Supporting human-in-the-loop interruptions
- Enabling state updates at specific nodes

**Subgraph state management:**
```python
# Get main state
main_state = graph.get_state(thread)
# Get subgraph checkpoint config from task
subgraph_checkpoint_config = main_state.tasks[0].state
# Update subgraph state
graph.update_state(subgraph_checkpoint_config, {"messages": [...]})
```

## Key Implementation Patterns

### Structured Output with Pydantic
All LLM calls use `.with_structured_output()` for type-safe responses:
```python
structured_llm = llm.with_structured_output(IntentClassificationOutput)
output = structured_llm.invoke(messages)
```

### Human-in-the-Loop
Graphs use `interrupt_before` to pause execution:
- Main graph: `interrupt_before=["user_input_clarity"]`
- Queue subgraph: `interrupt_before=["user_refine_search_query"]`

### Conditional Routing
Router functions return string keys mapped to next nodes:
```python
def routing_intent(state):
    if state['intent'] in ["document_accuracy", ...]:
        return "document parameters intent"
    return "search intent"
```

### Subgraph Integration
Subgraphs are created via factory functions and added as nodes:
```python
test_builder.add_node("processing_queue_attribute",
    create_queue_processing_graph(llm=llm, checkpointer=memory))
```

## External Integrations

**GraphQL API**:
- Endpoint: `https://dash-dev.staple.io/graphql`
- Used in `construct_queue_mapping` node to fetch available queues
- Requires authentication cookie in headers

## Testing and Development

When testing graph execution in notebooks:
- Use thread config: `thread = {"configurable": {"thread_id": "unique_id"}}`
- Visualize graphs: `Image(graph.get_graph(xray=1).draw_mermaid_png())`
- Check state: `graph.get_state(thread)`
- Resume from interrupts: `graph.invoke(None, thread)`
