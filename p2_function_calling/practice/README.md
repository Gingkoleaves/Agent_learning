# P2：工具接口与 MCP

## 直接开始

```powershell
conda activate agent-learn
python -m pip install -r p2_function_calling/practice/requirements.txt
python -m p2_function_calling.practice.mcp_client
python practice.py 2 run
python -m unittest p2_function_calling.practice.test_mcp -v
```

MCP client 演示不调用模型 API：启动 server、握手、发现工具、读取课程 resource、获取比较 prompt、搜索并读回段落。结果在 artifacts/mcp-client.json，协议操作记录在 artifacts/mcp-client.jsonl。

P2 run 默认通过 MCP 执行五个工具，新增 update_study_task 修改已有待办。MODEL_PROVIDER=scripted 使用现有模拟脚本（仅搜索再结束，不是完整创建任务演示）；MODEL_PROVIDER=deepseek 使用真实模型，产生 API 调用。模型选择和 F5 章节选择保持原来的配置。

## 和 P1 的差别

| 能力 | P1 | P2 |
| --- | --- | --- |
| 工具在哪执行 | 同一进程直接调用函数 | MCP server 独立进程 |
| 工具如何告诉模型 | 本地手写工具描述 | tools/list 自动发现，转成模型的 function schema |
| 工具范围 | 搜索、读段落 | 搜索、读段落、创建待办、读回待办 |
| 上下文入口 | 直接读取 corpus | 除工具外，resource 提供目录，prompt 提供可复用模板 |
| 请求结果 | 单个调用闭环 | 一轮多调用，按 call_id 关联每条结果 |
| 写入 | 无 | 保存任务、相同请求重试不重复写入；同 ID 不同内容拒绝 |

主循环仍然是模型→动作→观察，这一点本来就不应改变。P2 学的是循环之外的工具边界、协议与可靠性，不是另一种推理算法。

## 按什么顺序读代码

1. solution.py 的 run：选择 mcp（默认）或 local（对照）。
2. mcp_client.py 的 connect：使用当前 agent-learn 的 sys.executable 启动 server，初始化 session。
3. CourseClient.discover：拿到 server 工具名、描述、参数定义。
4. solution.py 的 _run_mcp：获取 resource，用发现的 schema 告诉模型，生成远程工具 registry。
5. _run_loop → dispatch_calls：模型提出工具调用，registry 将它交给 client.call_tool。
6. mcp_server.py 的装饰器函数：SDK 校验参数后执行工具，返回证据或持久化结果。
7. 观察传回模型，直到最终答案或预算耗尽。连接退出时 SDK 关闭会话与子进程。

async 是 MCP SDK 的接口要求。_run_mcp 把原来的同步模型循环放到 worker 线程，远程工具通过 run_coroutine_threadsafe 回到 MCP 会话所在事件循环；这样保留现有同步模型接口，也避免阻塞协议收发。

## host / client / server

- host：practice.py 启动的 P2 助手，负责模型、循环和业务流程。
- client：CourseClient + SDK ClientSession，负责握手、发现和协议请求。
- server：独立 Python 进程，提供五个 tool、course://catalog resource、compare_papers prompt。

模型生成工具调用属于 Function Calling；client/server 之间通信属于 MCP。二者在不同边界上一起工作。

## 调试

F5 选择第 2 章；在 solution.py 的 _run_mcp、_run_loop 和 mcp_client.py 的 call_tool 打断点。调试配置启用了子进程调试，也可在 mcp_server.py 工具函数里打断点。不要单独启动 server 期待打印回答：它会等待 stdio 协议输入。

在 data/input.json 加上 "transport": "local" 可运行本地调用对照；改回 "mcp" 或去掉该字段恢复默认。temporary 数据由 host 导出到 artifacts/mcp-corpus.jsonl，保证两种方式使用同一语料；tasks 保存在 artifacts/study_tasks.json。

## 已完成和仍需练习

已完成 MCP server/client、P2 Agent 路由、自动 schema 转换、多调用适配、host 管理写入操作及真实子进程集成测试。未替你完成 12 题标注、完整故障实验报告、工具选择对照、真实模型效果评测和 report.md。写入失败后模型结束回复返回 failed；通信失败且重试耗尽返回 outcome_unknown，并停止继续创建。completed 仍不等于答案语义评测通过。

## 写入编号与重试

模型只提供 title、due_date、source_ids；更新任务提供 task_id 和要修改的字段。模型不再提供 request_id/operation_id。每次运行由 host 生成新的 run_id，每次写入先把 operation_id 和固定参数写入 artifacts/write_operations.json，再发给 server。通信错误默认自动重试一次，沿用同一编号和参数；参数校验失败不会自动重试。

MCP server 的原始 schema 包含内部 operation_id；host 的 model_schemas() 删除该字段后才交给模型。server 在 study_tasks.json 的 operations 中保存原始参数与结果快照，修改任务后再重试旧创建，也不会发生参数误判。旧 tasks 和 request_ids 数据继续保留，不删除历史待办。

同一输入再次启动 practice.py 是一次新运行，可以创建新的待办；这不是原操作的通信重试。相似待办的业务去重没有自动启用。

若返回 outcome_unknown，取结果中的 operations[].operation_id，创建一个输入文件，例如：

```json
{"resume_operation_id": "返回的操作 UUID"}
```

运行 `python practice.py 2 run --input 该文件路径`。host 从日志加载原始编号与参数直接恢复，不让模型重新生成。操作记录和任务存储采用单 server 进程的文件持久化；多 server 并发共享文件需要后续改成事务数据库。

本实现固定官方 MCP Python SDK 1.30.0，使用其 v1 接口。参考：https://github.com/modelcontextprotocol/python-sdk/tree/v1.x 。
