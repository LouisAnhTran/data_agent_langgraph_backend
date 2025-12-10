"""Document Model Processing Subgraph for Data Agent

This subgraph handles the extraction and processing of document model information
from user search queries, mapping model names to their IDs via GraphQL API, and
extracting field-value pairs for document filtering.
"""

from typing import TypedDict, Annotated, Dict, List, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field
import requests

from src.config import settings
from src.graphs.prompts.extract_models_from_search_query import (
    MODELS_NAME_EXTRACTION_FROM_QUERY_PROMPT,
)
from src.graphs.prompts.extract_fields_values_from_search_query import (
    FIELD_VALUE_EXTRACTION_PROMPT,
)

from src.graphs.custom_reducers.reduce_search_payload import reduce_search_payload
from src.graphs.state_definitions.overall_state import SearchPayload
from src.config import settings

class DocumentModelOverallState(TypedDict):
    """Overall state for the document model processing subgraph"""
    # Reuse channels from main graph
    messages: Annotated[list, add_messages]
    search_attributes: Optional[list[str]]
    search_payload: Annotated[SearchPayload, reduce_search_payload]

    # Node-specific channels
    # Document models
    map_document_models_to_ids: Dict[str, str]
    extracted_document_models: List[str]
    map_extracted_document_models_to_ids: Dict[str, str]

    # Document fields levels
    map_document_model_fields_to_code: Dict[str, str]
    map_fields_to_values: List[Dict[str, str]]


class DocumentModelOutputState(TypedDict):
    """Output state for the document model processing subgraph"""
    # Reuse channels from main graph
    messages: Annotated[list, add_messages]
    search_attributes: Optional[list[str]]
    search_payload: Annotated[SearchPayload, reduce_search_payload]


# ============= Pydantic Models =============

class ExtractedModelNames(BaseModel):
    """Extracted model names from user query"""
    matched_extracted_model_names: List[str] = Field(
        default_factory=list,
        description="List of all extracted models"
    )
    reasoning: str = Field(
        description="Brief explanation of which model names were identified"
    )


class Item(BaseModel):
    """Field-value pair for document filtering"""
    name: str = Field(description="field or column of the document")
    value: str = Field(description="corresponding value of that column/field")


class ExtractedFieldsValues(BaseModel):
    """Extracted field-value pairs from user query"""
    extracted_fields_values: List[Item] = Field(
        default_factory=list,
        description="List of all extracted field-value pairs"
    )
    reasoning: str = Field(
        description="Brief explanation of which field-value pairs were identified"
    )


# ============= Node Functions =============

def construct_model_mapping(state: DocumentModelOverallState) -> dict:
    """Fetch model names and IDs from GraphQL API

    Args:
        state: Current document model processing state

    Returns:
        Dictionary containing mapping of model names to IDs
    """
    print("\n 💡 I am in construct_model_mapping node")

    print(" I am making GraphQL call to fetch model names and ids")

    url = "https://dash-dev.staple.io/graphql"

    query = """
    query getModelsForAnalyticsDashboard {
        models: getModels {
            id
            name
            __typename
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
    cookie_string = "__cfduid=1765196161.753.41.415118|92177388de9c0d9ffff64d7c4b776c11; __stripe_mid=b7c69d34-29c8-4cf2-b50e-79da18b1c18af4d1d9; crisp-client%2Fsession%2Fb5af01cf-848b-4812-b6b6-c1ee3aa52ffa=session_4b7eddcd-ba0e-4510-a7fd-f839a54ab19c; __t__SGDEV=Bearer%20eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOjEsImlkZW50aXR5IjoiMSIsImlhdCI6MTc2NTMxODkyOCwiZXhwIjoxNzY1MzYyMTI4fQ.yYkP4VbYfID0TdU_n8BKxHMy0yxLrdvtyvGJbORdL80"

    headers["Cookie"] = settings.cookie_string

    payload = {
        "operationName": "getModelsForAnalyticsDashboard",
        "query": query,
        "variables": {}
    }

    response = requests.post(
        url,
        json=payload,
        headers=headers
    )

    print(f"Status Code: {response.status_code}")

    map_document_models_to_ids = {}

    if response.status_code == 200:
        data = response.json()
        print("data: ", data)

        # Add null-safety checks
        if data and 'data' in data and data['data'] is not None:
            models = data['data'].get('models', None)
            if models is not None:
                map_document_models_to_ids = {
                    model_data["name"]: str(model_data["id"])
                    for model_data in models
                }

                # Add predefined document models
                map_document_models_to_ids.update(
                    {
                        predefine_model: "-1"
                        for predefine_model in settings.predefined_document_models
                    }
                )
            else:
                print("⚠ Warning: 'models' is None in response")
        elif data and 'errors' in data:
            print(f"❌ GraphQL errors: {data['errors']}")
        else:
            print(f"⚠ Unexpected response structure: {data}")
    else:
        print(f"Error: {response.text}")

    print("map_document_models_to_ids: ", map_document_models_to_ids)

    return {"map_document_models_to_ids": map_document_models_to_ids}


def extract_model_names_node(state: DocumentModelOverallState, llm) -> dict:
    """Extract model names from user query

    Args:
        state: Current document model processing state
        llm: Language model instance for extraction

    Returns:
        Dictionary containing extracted model names and reasoning
    """
    print("\n 🚀 I am in extracting model names from query")

    structured_llm = llm.with_structured_output(ExtractedModelNames)

    system_message = MODELS_NAME_EXTRACTION_FROM_QUERY_PROMPT.format(
        model_names=list(state["map_document_models_to_ids"].keys())
    )

    messages = [SystemMessage(content=system_message)] + state["messages"]

    result: ExtractedModelNames = structured_llm.invoke(messages)

    print(f"   Extracted model names: {result.matched_extracted_model_names}")
    print(f"   Reasoning: {result.reasoning}")

    extracted_document_models = []

    if not result.matched_extracted_model_names:
        print("   No model names found in query")
    else:
        model_count = len(result.matched_extracted_model_names)
        model_list = ", ".join(result.matched_extracted_model_names)
        print(f"   Found {model_count} model(s): {model_list}")

        extracted_document_models = result.matched_extracted_model_names

    return {
        "extracted_document_models": extracted_document_models,
        "messages": [AIMessage(content=result.reasoning)],
    }


def user_choose_from_all_dropdown(state: DocumentModelOverallState) -> dict:
    """Node for user to choose model from all available models

    Args:
        state: Current document model processing state

    Returns:
        Empty dictionary (state unchanged, waiting for user input)
    """
    return {}


def user_choose_from_extracted_dropdown(state: DocumentModelOverallState) -> dict:
    """Node for user to choose model from extracted models

    Args:
        state: Current document model processing state

    Returns:
        Empty dictionary (state unchanged, waiting for user input)
    """
    return {}


def map_extracted_document_model_to_ids(state: DocumentModelOverallState) -> dict:
    """Map extracted document model to its ID

    Args:
        state: Current document model processing state

    Returns:
        Dictionary containing mapping of extracted model to ID
    """
    print("\n 🚀 I am in map_extracted_document_model_to_ids")

    extracted_documents_models = state['extracted_document_models']

    map_extracted_document_models_to_ids = {"model": model for model in extracted_documents_models}

    map_extracted_document_models_to_ids.update({
        "id": state['map_document_models_to_ids'][map_extracted_document_models_to_ids['model']]
    })

    print("map_extracted_document_models_to_ids: ", map_extracted_document_models_to_ids)

    return {
        "map_extracted_document_models_to_ids": map_extracted_document_models_to_ids
    }


def retrieve_fields_colums_by_model(state: DocumentModelOverallState) -> dict:
    """Fetch field columns for the selected document model from GraphQL API

    Args:
        state: Current document model processing state

    Returns:
        Dictionary containing mapping of field names to codes
    """
    print("\n 💡 I am making GraphQL call to fetch all fields pertaining to a document model")

    url = "https://dash-dev.staple.io/graphql"

    query = """
    query getFieldsOfModel($mid: String!) {
        items: getFieldsByModelId(mid: $mid) {
            code
            name
            __typename
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
    cookie_string = "__cfduid=1765196161.753.41.415118|92177388de9c0d9ffff64d7c4b776c11; __stripe_mid=b7c69d34-29c8-4cf2-b50e-79da18b1c18af4d1d9; crisp-client%2Fsession%2Fb5af01cf-848b-4812-b6b6-c1ee3aa52ffa=session_4b7eddcd-ba0e-4510-a7fd-f839a54ab19c; __t__SGDEV=Bearer%20eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1aWQiOjEsImlkZW50aXR5IjoiMSIsImlhdCI6MTc2NTMxODkyOCwiZXhwIjoxNzY1MzYyMTI4fQ.yYkP4VbYfID0TdU_n8BKxHMy0yxLrdvtyvGJbORdL80"

    headers["Cookie"] = settings.cookie_string

    map_extracted_document_models_to_ids = state["map_extracted_document_models_to_ids"]

    payload = {
        "operationName": "getFieldsOfModel",
        "query": query,
        "variables": {
            "mid": (
                map_extracted_document_models_to_ids["model"]
                if map_extracted_document_models_to_ids["id"] == "-1"
                else map_extracted_document_models_to_ids["id"]
            )
        }
    }

    response = requests.post(
        url,
        json=payload,
        headers=headers
    )

    print(f"Status Code: {response.status_code}")

    map_document_model_fields_to_code = {}

    if response.status_code == 200:
        data = response.json()
        print("data: ", data)

        # Add null-safety checks
        if data and 'data' in data and data['data'] is not None:
            items = data['data'].get('items', None)
            if items is not None:
                map_document_model_fields_to_code = {
                    item["name"]: item["code"] for item in items
                }
            else:
                print("⚠ Warning: 'items' is None in response")
        elif data and 'errors' in data:
            print(f"❌ GraphQL errors: {data['errors']}")
        else:
            print(f"⚠ Unexpected response structure: {data}")
    else:
        print(f"Error: {response.text}")

    print("map_document_model_fields_to_code: ", map_document_model_fields_to_code)

    return {"map_document_model_fields_to_code": map_document_model_fields_to_code}


def extract_model_fields_and_values(state: DocumentModelOverallState, llm) -> dict:
    """Extract field-value pairs from user query

    Args:
        state: Current document model processing state
        llm: Language model instance for extraction

    Returns:
        Dictionary containing extracted field-value mappings and reasoning
    """
    print("\n 🚀 I am in extract_model_fields_and_values")

    structured_llm = llm.with_structured_output(ExtractedFieldsValues)

    system_message = FIELD_VALUE_EXTRACTION_PROMPT.format(
        field_names=list(state["map_document_model_fields_to_code"].keys())
    )

    messages = [SystemMessage(content=system_message)] + state["messages"]

    result: ExtractedFieldsValues = structured_llm.invoke(messages)

    print(f"   Extracted fields values pairs: {result.extracted_fields_values}")
    print(f"   Reasoning: {result.reasoning}")

    map_fields_to_values = []

    if not result.extracted_fields_values:
        print("   No field value pairs are extracted")
    else:
        pairs_count = len(result.extracted_fields_values)
        print(f"   Found {pairs_count} field-value pair(s)")

        for item in result.extracted_fields_values:
            print(f"   Field: {item.name} | Value: {item.value}")

        map_fields_to_values = [
            {
                "name": state["map_document_model_fields_to_code"][item.name],
                "value": item.value
            }
            for item in result.extracted_fields_values
        ]

    return {
        "map_fields_to_values": map_fields_to_values,
        "messages": [AIMessage(content=result.reasoning)],
    }


def user_specify_field_values_from_dropdown_list(state: DocumentModelOverallState) -> dict:
    """Node for user to specify field values from dropdown

    Args:
        state: Current document model processing state

    Returns:
        Empty dictionary (state unchanged, waiting for user input)
    """
    return {}


def user_confirm_extracted_field_values_pairs(state: DocumentModelOverallState) -> dict:
    """Node for user to confirm extracted field-value pairs

    Args:
        state: Current document model processing state

    Returns:
        Empty dictionary (state unchanged, waiting for user input)
    """
    return {}


def update_search_payload(state: DocumentModelOverallState) -> dict:
    """Update the search payload with extracted document model information

    Args:
        state: Current document model processing state

    Returns:
        Dictionary containing updated search payload and attributes
    """
    print("\n 🚀 I am in update_search_payload node")

    map_extracted_document_models_to_ids = state["map_extracted_document_models_to_ids"]
    search_attributes = state["search_attributes"]

    updated_search_attributes = [
        attr for attr in search_attributes if attr != "document_model"
    ]

    updated_search_payload = {}

    if map_extracted_document_models_to_ids["id"] == "-1":
        updated_search_payload["doctype"] = map_extracted_document_models_to_ids["model"]
    else:
        updated_search_payload["model_id"] = map_extracted_document_models_to_ids["id"]

    updated_search_payload.update({
        "fields": state['map_fields_to_values']
    })

    return {
        "search_payload": {"others": updated_search_payload},
        "search_attributes": updated_search_attributes,
    }


# ============= Router Functions =============

def routing_based_on_extracted_documents_models(state: DocumentModelOverallState) -> str:
    """Route based on extracted document models

    Args:
        state: Current document model processing state

    Returns:
        Route name indicating next node to execute
    """
    print("\n 🚀 I am in routing_based_on_extracted_documents_models")

    extracted_documents_models = state["extracted_document_models"]

    print("extracted_documents_models: ", extracted_documents_models)

    if not extracted_documents_models:
        print("there are no valid document models in user query")
        return "no models extracted - select from model dropdown list"

    if len(extracted_documents_models) > 1:
        print(
            "there are more than 1 document model extracted from query, system only allow maximum of 1 document model, ask user to finalize the document model"
        )
        return "more than 1 models extracted - select from extracted model dropdown list"

    print(
        "There is a single document model extracted - valid case - proceed to extracted column fields and values for filtering"
    )

    return "exactly 1 document model extracted"


def routing_based_on_extracted_field_value_pairs(state: DocumentModelOverallState) -> str:
    """Route based on extracted field-value pairs

    Args:
        state: Current document model processing state

    Returns:
        Route name indicating next node to execute
    """
    print("\n 🚀 I am in routing_based_on_extracted_field_value_pairs")

    map_fields_to_values = state["map_fields_to_values"]

    print("map_fields_to_values: ", map_fields_to_values)

    if not map_fields_to_values:
        print("there are no valid field values extracted from user query - show a list of field drop down and ask user to enter value")
        return "no field values extracted - select from dropdown list"

    print(
        "There are valid field values extracted from user query - ask user for confirmation"
    )

    return "valid field - value pair extracted - ask for confirmation"


# ============= Graph Builder =============

def create_document_model_processing_graph(llm=None, checkpointer=None):
    """Factory function to create the document model processing subgraph

    Args:
        llm: Language model to use (optional, defaults to configured model)
        checkpointer: Checkpointer for persistence (optional)

    Returns:
        Compiled LangGraph for document model processing
    """
    if llm is None:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=settings.default_llm_model,
            temperature=settings.default_llm_temperature,
            api_key=settings.openai_api_key
        )

    # Create wrapper functions that include llm
    def extract_model_names_with_llm(state: DocumentModelOverallState) -> dict:
        return extract_model_names_node(state, llm)

    def extract_model_fields_and_values_with_llm(state: DocumentModelOverallState) -> dict:
        return extract_model_fields_and_values(state, llm)

    # Build the graph
    doc_model_builder = StateGraph(
        state_schema=DocumentModelOverallState,
        output=DocumentModelOutputState
    )

    # Add nodes
    doc_model_builder.add_node("construct_model_mapping", construct_model_mapping)
    doc_model_builder.add_node("extract_model_names_node", extract_model_names_with_llm)
    doc_model_builder.add_node("user_choose_from_all_dropdown", user_choose_from_all_dropdown)
    doc_model_builder.add_node("user_choose_from_extracted_dropdown", user_choose_from_extracted_dropdown)
    doc_model_builder.add_node("map_extracted_document_model_to_ids", map_extracted_document_model_to_ids)
    doc_model_builder.add_node("retrieve_fields_colums_by_model", retrieve_fields_colums_by_model)
    doc_model_builder.add_node("extract_model_fields_and_values", extract_model_fields_and_values_with_llm)
    doc_model_builder.add_node("user_specify_field_values_from_dropdown_list", user_specify_field_values_from_dropdown_list)
    doc_model_builder.add_node("user_confirm_extracted_field_values_pairs", user_confirm_extracted_field_values_pairs)
    doc_model_builder.add_node("update_search_payload", update_search_payload)

    # Add edges
    doc_model_builder.add_edge(START, "construct_model_mapping")
    doc_model_builder.add_edge("construct_model_mapping", "extract_model_names_node")

    doc_model_builder.add_conditional_edges(
        "extract_model_names_node",
        routing_based_on_extracted_documents_models,
        {
            "no models extracted - select from model dropdown list": "user_choose_from_all_dropdown",
            "more than 1 models extracted - select from extracted model dropdown list": "user_choose_from_extracted_dropdown",
            "exactly 1 document model extracted": "map_extracted_document_model_to_ids",
        }
    )

    doc_model_builder.add_edge("user_choose_from_all_dropdown", "map_extracted_document_model_to_ids")
    doc_model_builder.add_edge("user_choose_from_extracted_dropdown", "map_extracted_document_model_to_ids")
    doc_model_builder.add_edge("map_extracted_document_model_to_ids", "retrieve_fields_colums_by_model")
    doc_model_builder.add_edge("retrieve_fields_colums_by_model", "extract_model_fields_and_values")

    doc_model_builder.add_conditional_edges(
        "extract_model_fields_and_values",
        routing_based_on_extracted_field_value_pairs,
        {
            "no field values extracted - select from dropdown list": "user_specify_field_values_from_dropdown_list",
            "valid field - value pair extracted - ask for confirmation": "user_confirm_extracted_field_values_pairs",
        }
    )

    doc_model_builder.add_edge("user_specify_field_values_from_dropdown_list", "update_search_payload")
    doc_model_builder.add_edge("user_confirm_extracted_field_values_pairs", "update_search_payload")
    doc_model_builder.add_edge("update_search_payload", END)

    # Compile
    graph = doc_model_builder.compile(
        interrupt_before=[
            "user_choose_from_all_dropdown",
            "user_choose_from_extracted_dropdown",
            "user_specify_field_values_from_dropdown_list",
            "user_confirm_extracted_field_values_pairs"
        ],
        checkpointer=checkpointer
    )

    return graph
