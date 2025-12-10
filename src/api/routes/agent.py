"""Agent endpoints for LangGraph chat interactions"""

import json
import uuid
from typing import Optional, AsyncGenerator
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

        # current graph state
        state = graph.get_state(thread)

        response_type = None
        action = None
        next_node = None

        # require human in the loop
        if state.next:
            next_node = state.next[0]

            logger.info(f"🍿 next node for humna in the loop {next_node}")

            response_type = "human_required"

            if next_node == "user_input_clarity":
                action = "user_freetext_input"
        else:
            response_type = "complete"

        # Send completion event
        completion_data = {
            "type": response_type,
            "action": action,
            "thread_id": thread_id,
            "next_node": next_node,
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
