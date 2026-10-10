# Agent 学习实践

完整任务见 [PRACTICE_TASKS.md](PRACTICE_TASKS.md)。六章在各自 `practice/` 中完成，算法与框架集成都由你实现。

## 开始运行

使用名为 `agent-learn` 的项目专用 Conda 环境（Python 3.11）。当前机器位置为 `D:\Miniconda3\envs\agent-learn`；首次克隆时在仓库根目录创建：

```powershell
conda env create --file environment.yml
conda activate agent-learn
```

随后可以使用激活环境的 `python`；推荐直接用下面的入口，它固定选择项目 Conda 解释器，避免 PATH 指向 base 或其它 Python：

```powershell
.\scripts\practice.ps1 1 status
.\scripts\practice.ps1 1 demo
.\scripts\practice.ps1 1 run
```

- `status` 显示作业清单，不自动判断作业完成。
- `demo` 只验证样例读写、模拟模型和日志，不调用真实模型，也不实现课程算法。
- `run` 调用你的 `solution.py`；遇到未完成部分，输出 TODO 编号并以退出码 2 结束。
- 将章节数字换成 2–6 即可。`--input 路径` 可覆盖输入 JSON。

## 文件职责

| 文件 | 职责 | 你要改吗 |
| --- | --- | --- |
| `practice_common/runtime.py` | JSON/JSONL、原子文件替换、模拟模型、日志、简单存储 | 通常不需要 |
| `data/corpus.jsonl` | 已有笔记导出的启动语料 | 要补原文和证据定位 |
| 各章 `practice/solution.py` | 核心算法与接口契约 | 必须实现所有 TODO |
| 各章 `practice/data/` | 少量样例输入、测例、模拟回复 | 要扩充、人工标注 |
| 各章 `practice/config.json` | 调用轮数、时间和上下文预算 | 算法必须真正执行这些限制 |
| 各章 `practice/report.md` | 对照结果、失败案例、完成记录 | 必须填写 |
| 各章 `practice/artifacts/` | 临时日志、数据库、索引、检查点 | 自动生成，Git 忽略 |

模拟模型只按脚本返回，不能证明智能体会选对工具。真实模型适配 TODO 在 `practice_common/model_adapter.py`；实现后在 CLI 中选择模拟/真实模式，用少量真实调用验证。统一 `respond(messages, tools=None)` 接口，保留调用计数、usage 和工具调用 ID。真实接口返回结构转换为课程代码使用的结构由你负责。

跨章复用示例：`from p1_basic_concepts.practice.solution import search_notes`。不要复制六套工具和数据库。模块导入时不要执行网络请求或启动服务。

每章 README 有准确 TODO 文件、建议顺序、扩充数据要求及验收入口。基础设施检查：

```powershell
conda activate agent-learn
python scripts/check_scaffold.py
```

该检查覆盖文件契约、模拟预算、存储、日志和未完成提示，不代替 [课程验收](PRACTICE_TASKS.md)。基础层无需安装第三方包；选定框架后在各章 `requirements.txt` 中锁定已验证版本，激活 `agent-learn` 后使用 `python -m pip install -r 章节/practice/requirements.txt` 安装。环境声明维护在 `environment.yml`；环境目录不提交 Git。原仓库 `.conda-env/` 是之前的环境副本，当前运行入口使用命名环境。

若当前机器的 `conda.exe` 启动失败，可通过已安装 Miniconda 的管理解释器运行 `D:\Miniconda3\python.exe -m conda create --name agent-learn --offline --copy --yes python=3.11 pip`，仅用于创建环境。课程运行始终使用 `agent-learn`，不使用 base。PowerShell 入口会从已激活环境、Miniconda 路径和 Conda 环境注册表中定位 `agent-learn`。

## 提交成果

保留代码、人工标注测例与报告。临时运行输出默认不提交；将报告需要的成功/失败轨迹从 `artifacts/` 复制到该章 `evidence/`，检查不含密钥再提交。不要把 `.env` 或 `api-key.txt` 写入代码或报告。
