# 调试

在 VS Code 打开整个 Agent_Learn 文件夹，设置断点后按 **F5**，依次选择章节和模型。模型选择 `scripted` 使用本地固定响应，选择 `deepseek` 使用根目录 `api-key.txt` 中的密钥调用真实模型。唯一配置始终启动根目录 practice.py，使用 agent-learn 环境，运行到你设置的断点时暂停。

- **F10**：执行下一行。
- **F11**：进入当前行调用的函数。进入 main() 后，在 module.run(...) 处按 F11 即进入所选章节的 solution.py。
- **F5**：继续到下一个断点；可以先在目标章节函数内设置断点。

使用 F5 或左侧“运行和调试”的绿色启动按钮。编辑器右上角的“调试 Python 文件”运行的是当前文件；在 solution.py 上使用它只会定义函数然后结束，不会执行本配置。

尚未实现的 run 会提示 TODO 后结束，这是课程代码的行为。函数未被调用时，内部断点不会命中。

需要 Python / Python Debugger 扩展（当前机器已安装）。换电脑时修改 launch.json 中的 python 路径。
