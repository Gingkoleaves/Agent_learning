# 2026年10月9日

## What's MCP

Model-Context-Protocal：为ai连接外部系统的开源标准

构成：mcp-host[ai application], mcp-server[application program provide context for ai], mcp-client[维护与mcp-server的连接并获取context供mcp-host使用]

> 例如：Visual Studio Code 充当 MCP 主机。当 Visual Studio Code 与 MCP 服务器（例如Sentry MCP 服务器）建立连接时，Visual Studio Code 运行时会实例化一个 MCP 客户端对象来维护与 Sentry MCP 服务器的连接。随后，当 Visual Studio Code 连接到另一个 MCP 服务器（例如本地文件系统服务器）时，Visual Studio Code 运行时会实例化另一个 MCP 客户端对象来维护此连接。

原语：server向client提供的带参数的接口api，server执行完后返回；定义原语使用json格式；提供/list方法查看server提供什么原语
tool【server执行某些函数并返回结果】、resource【server返回某些资源】、prompt【使用client提供的参数填入prompt并返回填充后的prompt】
此外还提供client向server订阅通知的功能，要求server在某些条件下向client主动通知，例如工具更新

## OpenAI function call

function-call大致流程：先把input和tools提供给llm，生成response【包含若干个item，是llm对工具的调用或返回的message】，并在input中记录请求response的过程；如果检测到response包含工具调用请求，就调用工具并补充到input.list；item处理完毕后再调用llm请求response获取最终答案
即定义函数需要的参数格式，让llm输出调用请求，本地调用后把结果返回llm重新生成最终答案；实际agent应当持续运行直到模型不在要求调用函数

## Toolformer：希望在生成文本时自动调用工具

提出自动调用工具的实现方法，是在输出文本时输出指定格式的api；一旦输出request-api就调用工具并把结果放在api后，llm考虑这些工具输出再继续输出
提出一种自监督的训练方法，对大量文本数据，让语言模型自动在不同位置生成api调用请求并把api返回结果插入，查看补充工具调用前后，llm对后续token的预测概率[加权]有没有上升[相比之前没有api调用，和只有请求没有返回]，只保留概率上升明显的api调用的插入文本；最后用这种含有api调用的文本训练模型

对一段原始文本，给少量示范要求生成带api的文本，然后teacher-force查看原文每个位置生成"["即api开始的概率，选top-k位置，每个位置生成若干api调用候选，调用工具后生成若干待选句子；对待选句子临时构造三种排列【没有调用，有调用无回答并把api请求[]放在句子前，有调用有回答[]放在句子前】，计算后续token的概率，选择待返回值-max(无请求,无答案)足够大的含回答句子，放回原位置来训练
