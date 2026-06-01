"""
LangGraph 入门示例 —— 一个带搜索工具的简单 Agent
运行: python langgraph_demo.py
"""
from typing import TypedDict, Literal, Annotated
import operator

from langgraph.graph import StateGraph, END

# 1. 定义共享状态
class AgentState(TypedDict):
    messages: Annotated[list, operator.add]  # 消息列表，自动追加
    tool_result: str
    step_count: int

# 2. 模拟 LLM 节点（实际使用时接入 OpenAI/DeepSeek）
def llm_node(state: AgentState) -> AgentState:
    last_msg = state["messages"][-1] if state["messages"] else ""
    step = state.get("step_count", 0)

    # 模拟 LLM 决策：第奇数步调用工具，偶数步输出最终答案
    if step < 2 and "天气" in last_msg:
        return {
            "messages": [f"[Agent 思考] 需要查询天气工具..."],
            "step_count": step + 1,
            "tool_result": ""
        }
    else:
        return {
            "messages": [f"[Agent 回答] 已为你查到相关信息！"],
            "step_count": step + 1,
            "tool_result": ""
        }

# 3. 模拟工具节点
def tool_node(state: AgentState) -> AgentState:
    return {
        "messages": [f"[工具返回] 北京今天晴，25°C"],
        "tool_result": "北京今天晴，25°C",
        "step_count": state["step_count"]
    }

# 4. 路由函数 —— 决定下一步走哪个节点
def router(state: AgentState) -> Literal["tools", "end"]:
    last = state["messages"][-1] if state["messages"] else ""
    if "需要查询" in last:
        return "tools"
    return "end"

# 5. 构建图
graph = StateGraph(AgentState)
graph.add_node("llm", llm_node)
graph.add_node("tools", tool_node)
graph.set_entry_point("llm")
graph.add_conditional_edges("llm", router, {"tools": "tools", "end": END})
graph.add_edge("tools", "llm")  # 工具执行完回到 LLM

app = graph.compile()

# 6. 运行
print("=" * 50)
print("LangGraph Agent 测试运行")
print("=" * 50)

result = app.invoke({
    "messages": ["北京今天天气怎么样？"],
    "tool_result": "",
    "step_count": 0
})

print("\n对话流程:")
for i, msg in enumerate(result["messages"]):
    print(f"  {i+1}. {msg}")

print(f"\n总步数: {result['step_count']}")
print("=" * 50)
print("LangGraph 运行成功！")
