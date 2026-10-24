# 2026年10月24日

如何评估agent的输出结果是否正确和稳定、出错溯因

## LangSmith: [https://docs.smith.langchain.com/]

支持多种框架，使用sdk提供性能监控[token消耗]和评测轨迹[函数调用顺序、输入输出和错误]
支持框架的意思是，可以通过环境变量的设置启动插桩，在agent框架运行完毕后导出funciton调用记录

## Tau-bench

面向两个业务场景提供[数据库、api、业务规则、用户背景和期望结果]，通过agent接受模拟用户发出的需求，并观察运行结果[在数据库、api上的结果]，是否与ground-truth的符合业务规则的操作的结果相同

## OpenTelemetry for LLM/Agent [https://opentelemetry.io/docs/]

一套采集和发送运行数据的标准与工具，提供api和sdk工具，可用于导出agent、http服务、数据库、后台任务等多种服务的调用链和统计指标
可以手动插桩，即在action中加入with语句获取异常，并在真正业务代码前后加上记录语句
