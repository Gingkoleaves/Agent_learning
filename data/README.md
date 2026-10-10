# 公共语料

`corpus.jsonl` 从已有三章 Markdown 笔记导出，字段为 doc_id、paragraph_id、source、text。它只用于脚手架启动，不等于论文原文或已经完成的 RAG 数据集。

你需要在第 1 章加入 3–5 份原始资料的可定位文本；第 3 章补充 chunk_id、页码等字段并建立至少 100 个 chunk 的索引。不要把自动分段数当成有效 chunk 数。正式问题与标准证据应人工核对。
