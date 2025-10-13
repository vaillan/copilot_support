from typing import Callable, Literal, TypedDict
from langchain_core.language_models.chat_models import BaseChatModel

from langgraph.graph import END
from langgraph.types import Command

from app.utils.state import ResearchState
from app.utils.files import File

def make_supervisor_node(llm: BaseChatModel, members: list[str]) -> Callable:
    file = File(directory="prompts")
    supervisor_prompt_content = file.get_file_content(file_name="supervisor_general_prompt.md")
    options = ["FINISH"] + members
    system_prompt = (supervisor_prompt_content)

    class Router(TypedDict):
        """Worker to route to next. If no workers needed, route to FINISH."""

        next: Literal[*options] # type: ignore

    async def supervisor_node(state: ResearchState) -> Command[Literal[*members, "__end__"]]: # type: ignore
        """An LLM-based router."""
        messages = [
            {"role": "system", "content": system_prompt},
        ] + state["messages"]
        response = await llm.with_structured_output(Router).ainvoke(messages)
        goto = response["next"] # type: ignore
        if goto == "FINISH":
            goto = END

        return Command(goto=goto, update={"next": goto})

    return supervisor_node # type: ignore