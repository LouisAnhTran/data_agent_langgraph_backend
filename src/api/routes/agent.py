"""Agent endpoints for LangGraph chat interactions"""

import json
import uuid
from typing import Dict, Optional, AsyncGenerator
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.config import settings
from langgraph.checkpoint.memory import MemorySaver
from src.graphs.main_graph import create_data_agent_graph
from src.utils.logger import get_logger

# Setup logger
logger = get_logger(__name__)

router = APIRouter()

# initialize LLM
llm = ChatOpenAI(
    model=settings.default_llm_model,
    temperature=settings.default_llm_temperature,
    api_key=settings.openai_api_key,
)

# initialize graph
memory = MemorySaver()

graph = create_data_agent_graph(llm=llm, checkpointer=memory)


class ChatRequest(BaseModel):
    """Chat request model"""

    user_query: str
    thread_id: Optional[str] = None
    next_node: Optional[str] = None
    map_extracted_queue_to_ids: Optional[Dict]=None


async def stream_graph_updates(
   thread_id: str,  user_query: Optional[str]=None
) -> AsyncGenerator[str, None]:
    """
    Stream graph state updates as Server-Sent Events

    Args:
        user_query: The user's query
        thread_id: Thread ID for conversation

    Yields:
        SSE formatted messages with state updates
    """
    try:
        thread = {"configurable": {"thread_id": thread_id}}

        logger.info(f"Starting graph stream for thread: {thread_id}")

        # Track streamed messages to avoid duplicates
        streamed_message_count = 0

        # Stream graph execution
        for chunk in graph.stream(
            {"messages": [HumanMessage(content=user_query)]} if user_query else None,
            thread,
            stream_mode="values",  # Stream full state values
        ):
            logger.debug(f"Received chunk: {chunk.keys()}")

            # Extract the latest message from the state
            if "messages" in chunk and chunk["messages"]:
                latest_message = chunk["messages"][-1]

                # Create response data
                response_data = {
                    "type": "message",
                    "content": latest_message.content,
                    "message_type": latest_message.__class__.__name__,
                    "thread_id": thread_id,
                }

                # Format as SSE
                yield f"data: {json.dumps(response_data)}\n\n"

                # Track how many messages we've streamed
                streamed_message_count = len(chunk["messages"])
                
        logger.info(f"streamed_message_count: {streamed_message_count}")

        # current graph state
        state = graph.get_state(thread)
        
        subgraph_state=None

        # Check for messages in interrupted subgraph state
        if state.next and state.tasks:
            logger.info(f"Graph interrupted at: {state.next[0]}")
            logger.info(f"Checking subgraph state for unstreamed messages...")

            # Get subgraph configuration
            subgraph_config = state.tasks[0].state
            
            logger.info(f"subgraph_config: {subgraph_config}")
            
            # Get the actual subgraph state using the config
            subgraph_state = graph.get_state(subgraph_config)
            
            if subgraph_state:
                # values is a method, not a property - need to call it
                subgraph_values = subgraph_state.values if isinstance(subgraph_state.values, dict) else subgraph_state.values()

                if subgraph_values and subgraph_values.get("messages"):
                    subgraph_messages = subgraph_values["messages"]
                    main_graph_message_count = len(state.values.get("messages", []))

                    logger.info(f"Subgraph has {len(subgraph_messages)} messages, main graph has {main_graph_message_count}")

                    # Subgraph messages include all messages from main graph + new ones
                    # Extract only the new messages added by subgraph
                    if len(subgraph_messages) > streamed_message_count:
                        logger.info(f"Found {len(subgraph_messages) - streamed_message_count} messages in interrupted subgraph")

                        # Stream messages that are only in subgraph
                        for message in subgraph_messages[main_graph_message_count:]:
                            response_data = {
                                "type": "message",
                                "content": message.content,
                                "message_type": message.__class__.__name__,
                                "thread_id": thread_id,
                            }
                            yield f"data: {json.dumps(response_data)}\n\n"
                            logger.info(f"Streamed subgraph message: {message.content[:100]}...")

        response_type = None
        action = None
        next_node = None
        map_queues_to_ids=None

        # require human in the loop
        if state.next:
            if not subgraph_state:
                next_node = state.next[0]

                logger.info(f"🍿 next node for humna in the loop {next_node}")

                response_type = "human_required"

                if next_node == "user_input_clarity":
                    action = "user_freetext_input"
            else:
                next_node = subgraph_state.next[0]

                logger.info(f"🍿 next node for humna in the loop {next_node}")
                
                response_type = "human_required"
                
                if next_node=="user_refine_search_query":
                    action = "list_down_queue"
                    
                    map_queues_to_ids=subgraph_values.get('map_queues_to_ids')
                    
                    


        else:
            response_type = "complete"

        # Send completion event
        completion_data = {
            "type": response_type,
            "action": action,
            "thread_id": thread_id,
            "next_node": next_node,
            "map_queues_to_ids": map_queues_to_ids
        }
        yield f"data: {json.dumps(completion_data)}\n\n"

        logger.info(f"Graph stream completed for thread: {thread_id}")

    except Exception as e:
        logger.error(f"Error in graph stream: {str(e)}", exc_info=True)
        error_data = {"type": "error", "error": str(e), "thread_id": thread_id}
        yield f"data: {json.dumps(error_data)}\n\n"


@router.post("/chat/stream")
async def chat_stream(user: ChatRequest):
    """
    Stream chat responses with state updates

    Returns Server-Sent Events (SSE) with each state update
    """
    logger.info(f"Received streaming chat request - Thread: {user.thread_id}")
    logger.info(f"User query: {user.user_query}")

    if not user.thread_id:
        thread_id = str(uuid.uuid4())

        return StreamingResponse(
            stream_graph_updates(user_query=user.user_query, thread_id=thread_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    # if thread id exists
    logger.info("thread id exists, continue the conversation")
    logger.info(f"next node for graph invocation - {user.next_node}")
    logger.info(f"user updated input query: {user.user_query}")

    if user.next_node == "user_input_clarity":
        thread = {"configurable": {"thread_id": user.thread_id}}

        graph.update_state(
            thread,
            {
                "messages": [
                    HumanMessage(
                        content=user.user_query
                    )
                ]
            },
        )
        
        return StreamingResponse(
            stream_graph_updates(user_query=None, thread_id=user.thread_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )
        
    if not user.next_node:
        logger.info("inside next node Null")
        return StreamingResponse(
            stream_graph_updates(user_query=user.user_query, thread_id=user.thread_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )
        


@router.post("/chat")
async def chat(user: ChatRequest):
    """
    Non-streaming chat endpoint (returns final result only)
    """
    # Generate thread_id if not provided
    thread_id = user.thread_id or str(uuid.uuid4())

    logger.info(f"Received chat request - Thread: {thread_id}")
    logger.debug(f"User query: {user.user_query}")

    try:
        thread = {"configurable": {"thread_id": thread_id}}

        logger.info("Processing chat request...")

        # Invoke graph and get final result
        result = graph.invoke(
            {"messages": [HumanMessage(content=user.user_query)]}, thread
        )

        logger.info("Chat request processed successfully")

        # Extract final messages
        final_messages = [
            {"content": msg.content, "type": msg.__class__.__name__}
            for msg in result.get("messages", [])
        ]

        return {
            "thread_id": thread_id,
            "messages": final_messages,
            "intent": result.get("intent"),
            "search_attributes": result.get("search_attributes"),
            "search_payload": result.get("search_payload"),
        }

    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
        raise
