# P3 base：按数据流单步观察

P3-01～05 已有可运行的基础实现；P3-06～10 的 MemGPT 工具循环仍是 TODO。本入口先观察普通工程 RAG，不做原始 RAG-Sequence/Token 训练或解码复现。

## 环境与首次准备

使用项目专用 `agent-learn` Python，不要使用 base：

```powershell
conda activate agent-learn
python -m pip install -r p3_memory_and_context/practice/requirements.txt
python -m p3_memory_and_context.practice.base_demo --prepare
```

本地 embedding 使用 FastEmbed 的 `BAAI/bge-small-zh-v1.5`（512 维，偏中文，适合当前中文笔记）；首次准备下载权重到本章 `artifacts/models/`，后续默认只读本地缓存。不保证中文模型对英文原论文达到同样检索质量。首次准备与实际运行分开，避免调试时等待下载。

DeepSeek 密钥读取 `DEEPSEEK_API_KEY`，或根目录已忽略的 `api-key.txt`。`MODEL_NAME` 默认 `deepseek-chat`；不自动读取 `.env`。只有 `--provider deepseek` 才会发送真实请求，发送内容是实际构造的上下文（学习档案、部分历史、检索笔记、问题）。每次运行最多调用一次聊天模型，并限制输出 token。

## 最小运行

先不调用聊天 API，查看真实本地向量检索与完整 prompt：

```powershell
python -m p3_memory_and_context.practice.base_demo --provider offline --step
```

接入 DeepSeek：

```powershell
python -m p3_memory_and_context.practice.base_demo --provider deepseek --step
```

每个阶段按 Enter 继续。若不想下载模型，可用 `--embedding hash` 调试协议；它是词面哈希特征，不是语义 embedding，不作为正式检索评测结果。

## VS Code Step Into

运行和调试选择 **P3 base：DeepSeek + 本地 embedding（单步）**，选择输入场景。先在 `solution.py` 的 `run` 函数内第一条语句打断点，然后 F5。F11 进入自写函数，F10 跳过网络或模型内部代码。

| 步骤 | 建议断点 | 重点观察 |
| --- | --- | --- |
| 1 | `update_profile` 返回前 | `profile.facts` 是有效值；`history` 保存被替换值及来源 |
| 2 | `build_index` 返回前 | `chunks` 的来源/段落/偏移，`vectors`，缓存摘要与模型标识 |
| 3 | `retrieve` 排序返回前 | 查询向量、余弦相似度、top-5；高分不等于足以回答 |
| 4 | `build_context` 返回前 | `messages` 是真正要发送的 prompt；只引用装得下的证据 |
| 5 | `model.respond` 前后 | 证据如何进入模型；真实 response 与 usage |
| 6 | `run` 返回前 | 引用 ID 校验、档案与历史落盘、最终状态 |

调试入口将总运行超时放宽为 3600 秒，以免断点暂停导致假超时；真实 HTTP 请求仍限制为 60 秒。普通演示总超时 120 秒。预算在模型返回后检查；标准库同步调用无法强制抢占底层计算。

## 三次运行观察持久化

分别选择或通过 `--input` 指定：

1. `data/base_input.json`：写入已读 ReAct、每天 45 分钟。
2. `data/base_update.json`：把时间改成 20 分钟，旧 45 分钟进入 history。
3. `data/base_recall.json`：不提供新事实，另起进程从磁盘读取现状。

例如：

```powershell
python -m p3_memory_and_context.practice.base_demo --provider deepseek --input p3_memory_and_context/practice/data/base_update.json
python -m p3_memory_and_context.practice.base_demo --provider deepseek --input p3_memory_and_context/practice/data/base_recall.json
```

再次运行 `base_input.json` 会显式把时间设置回 45 分钟，这不是记忆丢失。更换 `user_id` 可验证隔离。

## 输出文件

- `artifacts/index.json`：向量及来源，内容或模型改变会重建。
- `artifacts/profiles.json`：各用户的有效档案和变更历史。
- `artifacts/conversations.json`：成功获得生成回复的完整对话历史；不属于有限输入窗口。
- `artifacts/base_trace.jsonl`：每阶段观察，跨运行追加。
- `artifacts/base_result.json`：最近一次结果，包含实际上下文。

`offline_inspection` 只完成检索与组装，不会伪造回答或写入假的助手历史。`generated_ungraded` 表示真实/模拟模型生成完成，尚未评价语义正确性；`invalid_citations` 表示引用 ID 不在实际输入证据中。引用存在并不自动证明结论正确。

## 基础实现的边界

- `facts` 由输入显式提供；尚未让模型自主抽取、写入记忆。这是后续 MemGPT 实践的内容。
- 演示入口实时读取三章 Markdown 笔记，通用 `practice.py` 入口仍读取启动 corpus。尚未构建和人工核对 ≥100 个论文 chunk。
- 三种策略均保留当前有效档案和问题；变化的是历史处理：最近截断、摘录式摘要、摘录摘要加关键词相关历史召回。摘要目前是确定性的句子摘录，不是 LLM 生成摘要。
- 输入大小按 UTF-8 字节数做保守估计，不冒充 tokenizer 实测；DeepSeek 实际 usage 单独记录。演示输入总预算为 6000 个估计单位，预留 800 输出与 400 工具空间，剩余 4800 用于 prompt。
- 没有通过相似度阈值自动判定“有答案”；让生成器依据证据说明缺证。3 道无答案题与 15 道证据题的正式质量验收尚未完成。
- 用户数据是单进程 JSON 存储，不支持并发写入。未实现 MemGPT heartbeat/yield、记忆压力工具链或 agent 自主选择检索。

基础回归测试：

```powershell
python -m unittest p3_memory_and_context.practice.test_base -v
```

测试覆盖缓存失效、检索来源、档案更新与隔离、三个策略的预算、实际证据传入生成器、无效引用及调用预算；不把模拟模型测试当成真实回答质量。
