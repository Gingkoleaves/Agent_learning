# MCP 跨线程、跨进程断点接力

F5 选择第 2 章和 scripted。subProcess 已开启，server 必须由这个调试会话启动；单独从终端启动的 server 不会自动加入本次调试。

按代码语句设置断点，不依赖可能变化的行号：

1. solution.py，remote_tool 内的 call：future = asyncio.run_coroutine_threadsafe(...)。这里是助手工作线程。
2. mcp_client.py，CourseClient.call_tool：response = await self.session.call_tool(...)。这里是在助手主线程的事件循环中执行。
3. mcp_server.py，search_notes：return {'evidence': local_search(query, corpus)}。这里是 server 子进程；同步工具函数可由 SDK 安排在线程池执行。
4. mcp_client.py，result = response.structuredContent。这时 server 的响应已经回来。
5. solution.py，dispatch_calls：results.append({'call_id': call_id, 'name': name, 'result': result})。这时工作线程已拿到结果。

每到一个断点，查看 CALL STACK 中的调试会话、线程和栈帧，再按 F5 继续到下一站。F11 能进入同线程函数；不能顺着普通调用栈跨过线程调度或进程管道。必要时选择仍暂停的另一个会话，继续它。

在 Watch 添加：

```python
__import__('os').getpid()
__import__('threading').current_thread().name
__import__('threading').get_ident()
```

第 1、2、4、5 站 PID 相同；第 1、5 站在线程池工作线程，第 2、4 站在事件循环线程；第 3 站 PID 不同。在第 1/2 站观察 name、arguments；第 4 站观察 response；第 5 站观察 result 和 call_id。

同进程暂停可能暂停多个线程；另一个进程也可能因等待响应而停滞。停滞不等于逻辑死锁，先检查 CALL STACK 有没有未继续的调试会话。

F5 配置通过 MCP_DEBUG_TIMEOUT_SECONDS=3600 延长 MCP 会话及工作线程等待超时，避免查看变量超过默认 30 秒时误报失败。普通命令行仍使用 config 的超时；模型 HTTP 超时不受这个参数影响。

只观察业务调用不需要关闭 justMyCode。想进入官方 MCP SDK，再临时将其改为 false。
