# P3：RAG 与 MemGPT 学习实现

统一从根目录 `practice.py` 启动。VS Code 按 F5，选择章节中的 P3 RAG 或 P3 MemGPT，再选择模型。

## 阅读顺序

- `solution.py`：`run` 串联档案更新、索引、检索、上下文组装和回答；`launch` 负责读取启动配置。
- `memory.py`：`run_memory_agent` 是主循环；`manage_context` 管 FIFO；`execute_memory_tool` 修改档案或查询外部存储。
- `embeddings.py`：本地 BGE 向量，以及用于离线检查的 hash 向量。
- `evaluation.py`：合成场景的八项机制检查。

## 启动

```powershell
# 激活 agent-learn 环境后，在仓库根目录运行
python practice.py 3-rag run --provider deepseek
python practice.py 3-memgpt run --provider deepseek

# 无需 API 的演示和检查
python practice.py 3-rag run --provider offline
python practice.py 3-memgpt run --provider scripted
python practice.py 3-memgpt run --evaluate
```

`--mode rag|memgpt` 仍可搭配章节 `3`。F5 的模型选择由公共 CLI 传入 `launch(mode, provider, input_path)`。DeepSeek 固定搭配本地 BGE；scripted/offline 使用 hash 向量。密钥继续由已有适配器从环境变量或 api-key.txt 读取，不放进源代码。

默认 RAG 读取 `data/base_input.json` 和当前学习笔记。默认 MemGPT 创建独立合成场景，演示“更新当前档案 → 检索被移出的旧消息 → 读取原文 → 回复”。scripted 的工具选择是预先写好的，不代表模型推理。

只保留 `--mode`、`--provider`、`--input`、`--evaluate`。预算直接改 `config.json`；超时设为3600秒，方便停在断点观察；单次 HTTP 请求仍有45秒超时。已删除 `--embedding`、`--step`、`--prepare`、`--responses`、`--artifact-dir`。

结果在 `artifacts/rag` 或 `artifacts/memgpt`。MemGPT 合成演示另建子目录；自定义 `--input` 使用固定的 `artifacts/memgpt`，同一用户和会话 ID 可延续记忆。自定义模拟响应直接修改 `data/responses.json`；`DemoPolicy` 仅用于内置 MemGPT 场景。

本地 BGE 使用已有模型缓存。首次在新机器下载时，可在 Python 中运行 `from p3_memory_and_context.practice.embeddings import LocalEmbedding`，并在构造前设置 `P3_DOWNLOAD_MODEL=1`；日常启动无需设置。

## 简化边界

启动参数只在公共 CLI 解析一次。输入 JSON 和模型适配器按约定提供数据；已移除通用工具参数校验器、调用 ID 去重缓存、档案暂存事务、API embedding 和外围异常兜底。Python 异常直接定位到代码行，适合单步调试。

保留来源消息检查、用户隔离、上下文容量、分页读取和循环上限。工具执行仍返回简短错误，让模型能在下一次 heartbeat 修正调用。完整工具调用和返回结果一起进入 FIFO；移出 FIFO 前原始消息已写入 recall。

Token 预算使用 UTF-8 字节数作保守估计。摘要是截取原句。机制检查不代表正式问答质量评测；hash 向量也不代表语义检索质量。
