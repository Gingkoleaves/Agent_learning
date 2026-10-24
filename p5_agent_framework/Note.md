# 2026年10月22日

主流开源框架的选型与使用：LangGraph、CrewAI、AutoGen、Claude Agent SDK

## LangGraph 官方文档 [https://langchain-ai.github.io/langgraph/]

见之前记录 [https://github.com/Gingkoleaves/TJ_Try_MultiAgent/]

## LangGraph GitHub [https://github.com/langchain-ai/langgraph]

见之前记录 [https://github.com/Gingkoleaves/TJ_Try_MultiAgent/]

## OpenAI Agents SDK [https://openai.github.io/openai-agents-python/]

OpenAI Agents SDK让您能够使用一个轻量、易用且仅包含极少抽象概念的软件包，构建智能体式 AI 应用。它是我们之前智能体实验项目Swarm的生产就绪升级版。Agents SDK 仅包含一小组基础组件：

- 智能体，即配备了指令和工具的 LLM
- Agents as tools / 任务转移，允许智能体将特定任务委派给其他智能体
- 安全防护措施，用于验证智能体的输入和输出

这些基础组件与 Python 结合使用时，足以表达工具与智能体之间的复杂关系，让您无需经历陡峭的学习曲线即可构建实际应用。此外，SDK 还内置了追踪功能，让您能够可视化和调试智能体流程、对其进行评估，甚至针对您的应用微调模型。
