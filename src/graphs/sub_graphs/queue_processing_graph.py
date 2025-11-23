"""Queue Processing Subgraph for Data Agent

This subgraph handles the extraction and processing of queue information
from user search queries, mapping queue names to their IDs via GraphQL API.
"""

from typing import TypedDict, Annotated, Dict, List, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field
import requests

from src.config import settings
from src.graphs.prompts.extract_queues_from_search_query import QUEUES_NAME_EXTRACTION_FROM_QUERY_PROMPT

from src.graphs.custom_reducers.reduce_search_payload import reduce_search_payload
from src.graphs.state_definitions.overall_state import SearchPayload

class QueueOverallState(TypedDict):
    """Overall state for the queue processing subgraph"""
    # Reuse channels from main graph
    messages: Annotated[list, add_messages]
    search_attributes: Optional[list[str]]
    search_payload: Annotated[SearchPayload, reduce_search_payload]

    # Node-specific channels
    map_queues_to_ids: Dict[str, str]
    map_extracted_queue_to_ids: Dict[str, str]


class QueueOutputState(TypedDict):
    """Output state for the queue processing subgraph"""
    # Reuse channels from main graph
    messages: Annotated[list, add_messages]
    search_attributes: Optional[list[str]]
    search_payload: Annotated[SearchPayload, reduce_search_payload]


# ============= Pydantic Models =============

class ExtractedQueueNames(BaseModel):
    """Extracted queue names from user query"""
    matched_extracted_queue_names: List[str] = Field(
        default_factory=list,
        description="List of all extracted queues"
    )
    reasoning: str = Field(
        description="Brief explanation of which queue names were identified"
    )


# ============= Node Functions =============

def construct_queue_mapping(state: QueueOverallState) -> dict:
    """Fetch queue names and IDs from GraphQL API

    Args:
        state: Current queue processing state

    Returns:
        Dictionary containing mapping of queue names to IDs
    """
    print("\n 💡 I am in construct_queue_mapping node")

    print(" I am making graph QL call to fetch queue names and ids")

    url = "https://dash-dev.staple.io/graphql"

    query = """
    query getSelectableQueues {
        queues: getAssignedQueues {
            id
            name
        }
    }
    """

    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/json",
        "User-Agent": "PostmanRuntime/7.47.1"
    }

    # Full cookie string from Postman
    cookie_string = "__cfduid=1763862616.948.43.883255|92177388de9c0d9ffff64d7c4b776c11; __stripe_mid=b7c69d34-29c8-4cf2-b50e-79da18b1c18af4d1d9; crisp-client%2Fsession%2Fb5af01cf-848b-4812-b6b6-c1ee3aa52ffa=session_25d399fc-8e6f-442c-ae36-28653177ec93; __t__SGDEV=Bearer%20eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOjEsImlkZW50aXR5IjoiMSIsImlhdCI6MTc2Mzg4ODg3NiwiZXhwIjoxNzYzOTMyMDc2fQ.Itvj4rIJHCFfAuGxmLYrS1DVxBzLXgptD1vkeYWMByA"


    headers["Cookie"] = cookie_string

    payload = {
        "operationName": "getSelectableQueues",
        "query": query,
        "variables": {}
    }

    response = requests.post(
        url,
        json=payload,
        headers=headers
    )

    print(f"Status Code: {response.status_code}")

    mapping_queue_name_ids = {}

    if response.status_code == 200:
        data = response.json()
        print("data: ", data)

        # Add null-safety checks
        if data and 'data' in data and data['data'] is not None:
            queues = data['data'].get('queues', None)
            if queues is not None:
                mapping_queue_name_ids = {
                    queue_data["name"]: queue_data["id"]
                    for queue_data in queues
                }
            else:
                print("� Warning: 'queues' is None in response")
        elif data and 'errors' in data:
            print(f"� GraphQL errors: {data['errors']}")
        else:
            print(f"� Unexpected response structure: {data}")
    else:
        print(f"Error: {response.text}")

    print("mapping_queue_name_ids: ", mapping_queue_name_ids)

    return {"map_queues_to_ids": mapping_queue_name_ids}


def extract_queue_names_node(state: QueueOverallState, llm) -> dict:
    """Extract queue names from user query

    Args:
        state: Current queue processing state
        llm: Language model instance for extraction

    Returns:
        Dictionary containing extracted queue name mappings and reasoning
    """
    print("\n 🚀 I am in extracting queue names from query")

    structured_llm = llm.with_structured_output(ExtractedQueueNames)

    system_message = QUEUES_NAME_EXTRACTION_FROM_QUERY_PROMPT.format(
        queue_names=list(state["map_queues_to_ids"].keys())
    )

    messages = [SystemMessage(content=system_message)] + state["messages"]

    result: ExtractedQueueNames = structured_llm.invoke(messages)

    print(f"   Extracted queue names: {result.matched_extracted_queue_names}")
    print(f"   Reasoning: {result.reasoning}")

    map_extracted_queue_to_ids = {}

    if not result.matched_extracted_queue_names:
        print("   No queue names found in query")
    else:
        queue_count = len(result.matched_extracted_queue_names)
        queue_list = ', '.join(result.matched_extracted_queue_names)
        print(f"   Found {queue_count} queue(s): {queue_list}")

        map_extracted_queue_to_ids = {
            extracted_queue_name: state['map_queues_to_ids'].get(extracted_queue_name, None)
            for extracted_queue_name in result.matched_extracted_queue_names
        }

    return {
        "map_extracted_queue_to_ids": map_extracted_queue_to_ids,
        "messages": [AIMessage(content=result.reasoning)],
    }


def user_refine_search_query(state: QueueOverallState) -> dict:
    """Node for user to refine their search query

    Args:
        state: Current queue processing state

    Returns:
        Empty dictionary (state unchanged, waiting for user input)
    """
    return {}


def update_search_payload(state: QueueOverallState) -> dict:
    """Update the search payload with extracted queue information

    Args:
        state: Current queue processing state

    Returns:
        Dictionary containing updated search payload and attributes
    """
    print("\n 🚀 I am in update_search_payload node")

    map_extracted_queue_to_ids = state['map_extracted_queue_to_ids']
    search_attributes = state['search_attributes']

    updated_search_attributes = [attr for attr in search_attributes if attr != "queue"]

    return {
        "search_payload": {
            "queues": map_extracted_queue_to_ids
        },
        "search_attributes": updated_search_attributes
    }


# ============= Router Functions =============

def routing_queue_processing(state: QueueOverallState) -> str:
    """Route based on whether valid queues were extracted

    Args:
        state: Current queue processing state

    Returns:
        Route name indicating next node to execute
    """
    print("\n 🚀 I am in routing_queue_processing node")

    map_extracted_queue_to_ids = state['map_extracted_queue_to_ids']
    
    print("map_extracted_queue_to_ids: ",map_extracted_queue_to_ids)

    if not map_extracted_queue_to_ids or not all(list(map_extracted_queue_to_ids.values())):
        print("no queues extracted - request user to refine query")
        return "no queues extracted - user to refine query"
    
    print("correct queues extracted - go to update search payload")
    
    return "correct queues extracted - update search payload"


# ============= Graph Builder =============

def create_queue_processing_graph(llm=None, checkpointer=None):
    """Factory function to create the queue processing subgraph

    Args:
        llm: Language model to use (optional, defaults to configured model)
        checkpointer: Checkpointer for persistence (optional)

    Returns:
        Compiled LangGraph for queue processing
    """
    if llm is None:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=settings.default_llm_model,
            temperature=settings.default_llm_temperature,
            api_key=settings.openai_api_key
        )

    # Create wrapper functions that include llm
    def extract_queue_names_with_llm(state: QueueOverallState) -> dict:
        return extract_queue_names_node(state, llm)

    # Build the graph
    queue_builder = StateGraph(
        state_schema=QueueOverallState,
        output=QueueOutputState
    )

    # Add nodes
    queue_builder.add_node("construct_queue_mapping", construct_queue_mapping)
    queue_builder.add_node("extract_queue_names", extract_queue_names_with_llm)
    queue_builder.add_node("user_refine_search_query", user_refine_search_query)
    queue_builder.add_node("update_search_payload", update_search_payload)

    # Add edges
    queue_builder.add_edge(START, "construct_queue_mapping")
    queue_builder.add_edge("construct_queue_mapping", "extract_queue_names")

    queue_builder.add_conditional_edges(
        "extract_queue_names",
        routing_queue_processing,
        {
            "no queues extracted - user to refine query": "user_refine_search_query",
            "correct queues extracted - update search payload": "update_search_payload"
        }
    )

    queue_builder.add_edge("user_refine_search_query", "extract_queue_names")
    queue_builder.add_edge("update_search_payload", END)

    # Compile
    graph = queue_builder.compile(
        interrupt_before=["user_refine_search_query"],
        checkpointer=checkpointer
    )

    return graph
