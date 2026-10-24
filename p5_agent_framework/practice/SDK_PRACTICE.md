# P5-03：用 OpenAI Agents SDK 做一个学习计划助手

## 实践目标

输入主题、学习档案和起始日期，让模型通过 SDK 调用本地检索工具，使用返回的材料生成三天计划。理解 `Agent` 定义行为、`function_tool` 暴露能力、`Runner` 执行模型与工具交互的分工。

## 运行

```powershell
conda activate agent-learn
python -m pip install -r p5_agent_framework/practice/requirements.txt
.\scripts\practice.ps1 5 run --provider offline --input p5_agent_framework/practice/data/sdk-input.json
```

模型接口支持异步取消。离线模式无需密钥，会演示一次检索调用和一次计划生成；真实模式使用 `--provider deepseek` 和已有密钥配置。离线跑通只能证明 SDK 流程可运行，不代表真实模型能力。

## 按这条执行链读代码

1. `solution.py:run_agents_sdk` 进入 `agents_sdk.py:execute`，读取问题和档案。
2. `@function_tool` 将 `search_notes(query)` 注册为 SDK 工具，复用实际语料检索。结果保留 doc_id、paragraph_id 和正文。
3. `Agent` 绑定提示词、模型和工具；`Runner.run` 调用模型。模型输出 function call 后，由 Runner 执行工具并把结果传回。
4. `CourseModel` 负责 SDK Responses item 与项目模型接口的格式转换，保留 call_id、工具结果和 usage。真实 DeepSeek 与离线模型共用这个桥接层。
5. Runner 得到最终输出后，复用 `validate_plan` 检查连续日期、每日时长及引用来源，输出 `planned` 或明确失败状态。

## 动手内容

修改 `data/sdk-input.json` 中的 query、question、minutes_per_day 和 start_date，运行后查看候选计划。再打开 `artifacts/run.jsonl` 的 `sdk_run_items`：找到 function_call、对应 call_id 的 function_call_output，以及最终 message，理解工具结果怎样进入下一次模型请求。

查看 `metrics` 的模型调用、工具调用和实际 usage。离线模式 usage 不可用。最大调用数、轮数、超时和上下文预算沿用 `config.json`；耗尽时返回明确状态。

这里不保存任务，也不实现持久化恢复；这两项继续在 LangGraph 实践中学习。不增加 baseline、评测或功能测试代码。

参考：[OpenAI Agents SDK 的运行循环](https://developers.openai.com/api/docs/guides/agents/running-agents)。
