
from src.graphs.main_graph.data_agent_graph import create_data_agent_graph
from src.config import settings
from langchain_openai import ChatOpenAI

# initialize LLM
llm = ChatOpenAI(
    model=settings.default_llm_model,
    temperature=settings.default_llm_temperature,
    api_key=settings.openai_api_key,
)

# initialize graph
# Note: checkpointer is handled automatically by LangGraph Studio
graph = create_data_agent_graph(llm=llm, checkpointer=None,studio=True)

