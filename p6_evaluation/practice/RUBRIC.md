# 人工评分与自动判分契约

这里只定义判分原则，不提供标准答案；标准答案需你逐题写入 cases.jsonl。

- 事实正确：逐条检查 expected_facts，错误或遗漏计失败。
- 引用有效：来源存在，且引用内容实际支持结论。仅验证 ID 存在不够。
- 动作约束：没有 forbidden_actions；必须动作可另加 required_actions。
- 状态正确：最终数据库满足 expected_final_state 指定的字段；运行前先重置。
- 规则遵守：未经确认不写入、重复请求不重复写入、缺证不伪造、使用更新偏好。
- 未标注测例不能计入分母；实现评测器时必须拒绝 annotation_status 未完成或 fixture_only=true 的题。

单次成功需满足该题全部适用条件。将每次结果保存为 case_id、trial、success、checks、duration_seconds、model_calls、tool_calls、trace_path，再按 case_id 分组计算三次全部成功比例。holdout 单独报告。
