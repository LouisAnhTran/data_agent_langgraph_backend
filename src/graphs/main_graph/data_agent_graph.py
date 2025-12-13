"""Data Agent Main Graph

This is the main LangGraph workflow for the data analysis agent. It orchestrates
the intent classification, search attribute extraction, and routing to specialized
subgraphs for processing different types of search attributes.
"""

from typing import TypedDict, Annotated, List, Optional, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from src.config import settings
from src.graphs.prompts.intent_classification import INTENT_CLASSIFICATION_PROMPT
from src.graphs.prompts.search_attributes_extraction import SEARCH_ATTRIBUTES_EXTRACTION_PROMPT
from src.graphs.custom_reducers.reduce_search_payload import reduce_search_payload
from src.graphs.state_definitions.overall_state import SearchPayload
from src.graphs.sub_graphs.queue_processing_graph import create_queue_processing_graph
from src.graphs.sub_graphs.document_model_processing_graph import create_document_model_processing_graph


# ============= State Definition =============

class OverallState(TypedDict):
    """Main state for the data agent graph"""
    messages: Annotated[list, add_messages]
    intent: Optional[str]
    search_attributes: Optional[list[str]]
    search_payload: Annotated[SearchPayload, reduce_search_payload]


# ============= Pydantic Models =============

class IntentClassificationOutput(BaseModel):
    """Intent classification output from LLM"""
    intent: Literal["search", "document_accuracy", "document_counter", "document_processing_time", "others"] = Field(
        ...,
        description="The user's intent based on the conversation."
    )
    reasoning: str = Field(..., description="The reasoning behind the intent classification.")


class AttributesExtraction(BaseModel):
    """Search attributes extraction output from LLM"""
    attributes: List[Literal["document_model", "queue", "date"]] = Field(
        description="The attributes that need to be extracted. Must only contain: document model, queue, or date"
    )
    reasoning: str


# ============= Node Functions =============

def intent_classifier(state: OverallState, llm) -> dict:
    """Classify the user's intent from their message

    Args:
        state: Current graph state
        llm: Language model instance for classification

    Returns:
        Dictionary containing classified intent and reasoning
    """
    print("\n 🟢 I am in intent classifier node")

    structured_llm = llm.with_structured_output(IntentClassificationOutput)

    output = structured_llm.invoke([SystemMessage(content=INTENT_CLASSIFICATION_PROMPT)] + state["messages"])

    print("llm_output: ", output)

    return {"intent": output.intent, "messages": [AIMessage(content=output.reasoning)]}


def user_input_clarity(state: OverallState) -> dict:
    """Node for user to clarify their input when intent is unclear

    Args:
        state: Current graph state

    Returns:
        Empty dictionary (state unchanged, waiting for user input)
    """
    return {}


def extract_search_attributes_from_query(state: OverallState, llm) -> dict:
    """Extract search attributes (document_model, queue, date) from user query

    Args:
        state: Current graph state
        llm: Language model instance for extraction

    Returns:
        Dictionary containing extracted attributes and reasoning
    """
    print("\n 🍿 I am in extracting search attributes from query node")

    # Use structured output with Pydantic
    structured_llm = llm.with_structured_output(AttributesExtraction)

    messages = [SystemMessage(content=SEARCH_ATTRIBUTES_EXTRACTION_PROMPT)] + state['messages']

    result: AttributesExtraction = structured_llm.invoke(messages)

    print("extracted attributed result: ", result)

    if not result.attributes:
        print("There are no valid attributes can be extracted from your query")
    else:
        print(f"Valid extracted attributes: {', '.join(result.attributes)}")

    return {
        "search_attributes": result.attributes,
        "messages": [AIMessage(content=result.reasoning)]
    }


def router_processing_search_attributes(state: OverallState) -> dict:
    """Router node that doesn't modify state, just routes to next processing step

    Args:
        state: Current graph state

    Returns:
        Empty dictionary (no state changes)
    """
    return {}


# ============= Router Functions =============

def routing_intent(state: OverallState) -> str:
    """Route based on classified intent

    Args:
        state: Current graph state

    Returns:
        Route name indicating next node to execute
    """
    print("\n ⭐ I am in routing intent")

    if state['intent'] in ["document_accuracy", "document_counter", "document_processing_time"]:
        print("routing business parameters intent")
        return "document parameters intent"

    if state['intent'] == 'others':
        # human in the loop ask user to input again
        print("intent is unclear, request user query refinement")
        return "unclear intent"

    print("routing to search intent")
    return "search intent"


def routing_extracted_search_attributes(state: OverallState) -> str:
    """Route based on whether valid search attributes were extracted

    Args:
        state: Current graph state

    Returns:
        Route name indicating next node to execute
    """
    print("\n 🍺 I am in routing extracted search attributes")

    search_attributes = state['search_attributes']

    if not search_attributes:
        print("There are no valid search attributes")
        print("request user query refinement")
        return "vague search query"

    print("valid search query => routing to processing search attributes")
    return "valid search query"


def routing_processing_search_attributes(state: OverallState) -> str:
    """Route to appropriate attribute processing subgraph

    Args:
        state: Current graph state

    Returns:
        Route name indicating which subgraph to execute
    """
    print("\n 🔥 I am in routing processing search attributes")

    search_attributes = state['search_attributes']

    if not search_attributes:
        print("complete all processing")
        return "complete processing"

    if "queue" in search_attributes:
        print("routing to queue processing sub graph")
        return "processing queue attribute"

    if "document_model" in search_attributes:
        print("routing to document model processing sub graph")
        return "processing document model attribute"

    # If no matching attributes, complete processing
    print("complete all processing")
    return "complete processing"


# ============= Graph Builder =============

def create_data_agent_graph(llm=None, checkpointer=None,studio=False):
    """Factory function to create the main data agent graph

    Args:
        llm: Language model to use (optional, defaults to configured model)
        checkpointer: Checkpointer for persistence (optional, defaults to MemorySaver)

    Returns:
        Compiled LangGraph for data agent workflow
    """
    if llm is None:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=settings.default_llm_model,
            temperature=settings.default_llm_temperature,
            api_key=settings.openai_api_key
        )

    if checkpointer is None and not studio:
        checkpointer = MemorySaver()

    # Create wrapper functions that include llm
    def intent_classifier_with_llm(state: OverallState) -> dict:
        return intent_classifier(state, llm)

    def extract_search_attributes_with_llm(state: OverallState) -> dict:
        return extract_search_attributes_from_query(state, llm)

    # Build the main graph
    graph_builder = StateGraph(OverallState)

    # Add nodes
    graph_builder.add_node("intent_classifier", intent_classifier_with_llm)
    graph_builder.add_node("user_input_clarity", user_input_clarity)
    graph_builder.add_node("extract_search_attributes_from_query", extract_search_attributes_with_llm)
    graph_builder.add_node("router_processing_search_attributes", router_processing_search_attributes)
    graph_builder.add_node("processing_queue_attribute", create_queue_processing_graph(llm=llm, checkpointer=checkpointer))
    graph_builder.add_node("processing_document_model_attribute", create_document_model_processing_graph(llm=llm, checkpointer=checkpointer))

    # Add edges
    graph_builder.add_edge(START, "intent_classifier")

    graph_builder.add_conditional_edges(
        "intent_classifier",
        routing_intent,
        {
            "unclear intent": "user_input_clarity",
            "search intent": "extract_search_attributes_from_query",
            "document parameters intent": END
        }
    )

    graph_builder.add_edge("user_input_clarity", "intent_classifier")

    graph_builder.add_conditional_edges(
        "extract_search_attributes_from_query",
        routing_extracted_search_attributes,
        {
            "vague search query": "user_input_clarity",
            "valid search query": "router_processing_search_attributes"
        }
    )

    graph_builder.add_conditional_edges(
        "router_processing_search_attributes",
        routing_processing_search_attributes,
        {
            "processing queue attribute": "processing_queue_attribute",
            "processing document model attribute": "processing_document_model_attribute",
            "complete processing": END
        }
    )

    graph_builder.add_edge("processing_queue_attribute", "router_processing_search_attributes")
    graph_builder.add_edge("processing_document_model_attribute", "router_processing_search_attributes")

    # Compile
    if checkpointer:
        graph = graph_builder.compile(
        interrupt_before=["user_input_clarity"],
        checkpointer=checkpointer
    )
    else:
        graph = graph_builder.compile(
        interrupt_before=["user_input_clarity"]        
    )
        
    return graph
