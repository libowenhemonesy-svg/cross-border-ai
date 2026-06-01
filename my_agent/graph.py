"""LangGraph Agent — 在 Studio UI 中可视化编辑"""
from typing import TypedDict, Literal, Annotated
import operator

from langgraph.graph import StateGraph, END


class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    step_count: int


def llm_node(state: AgentState) -> AgentState:
    """LLM 推理节点"""
    last_msg = state["messages"][-1] if state["messages"] else ""
    step = state.get("step_count", 0)

    if step < 2 and ("天气" in last_msg or "搜索" in last_msg):
        return {
            "messages": ["[Agent] 需要调用工具查询..."],
            "step_count": step + 1
        }
    return {
        "messages": ["[Agent] 这是最终回答：已为你查到信息！"],
        "step_count": step + 1
    }


def tool_node(state: AgentState) -> AgentState:
    """工具执行节点"""
    return {
        "messages": ["[工具] 查询结果：北京晴 25°C"],
        "step_count": state["step_count"]
    }


def router(state: AgentState) -> Literal["tools", "__end__"]:
    """路由：是否需要调用工具"""
    last = state["messages"][-1] if state["messages"] else ""
    if "需要调用工具" in last:
        return "tools"
    return "__end__"


graph = StateGraph(AgentState)
graph.add_node("llm", llm_node)
graph.add_node("tools", tool_node)
graph.set_entry_point("llm")
graph.add_conditional_edges("llm", router, {"tools": "tools", "__end__": END})
graph.add_edge("tools", "llm")

app = graph.compile()
