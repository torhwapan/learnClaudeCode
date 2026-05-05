一，问题：
多步任务中, 模型会丢失进度 -- 重复做过的事、跳步、跑偏。对话越长越严重: 工具结果不断填满上下文, 系统提示的影响力逐渐被稀释。一个 10 步重构可能做完 1-3 步就开始即兴发挥, 因为 4-10 步已经被挤出注意力了。


二，解决方案：
1， system 定义改变!!!!!!!!!!!!!!!!   告诉模型，必须按步骤来执行
eg: SYSTEM = f"""You are a coding agent at {WORKDIR}.
Use the todo tool to plan multi-step tasks. Mark in_progress before starting, completed when done.
Prefer tools over prose."""


2, 定义一个 todo 工具，用来管理任务的状态。这时，整个工作流变成了：
step1, 用户发起一个任务
step2, system prompat 明确要求，先用todo规划，再做事
step3, 模型先调用 todo(items=[....])，把计划外显化
step4，TodoManager.update()校验并且提交计划，render()返回愿望清单
step5, 模型看到清单后，再根据清单调用 bash, read_file等工具
step6, 每做完一步，大模型会再调用一次todo工具，把某项从 in_process 改成 completed，把下一项设置成in_process
step7, 同时，如果连续3轮忘记了更新计划，会把模型拉回"先更新状态再继续"


三，实际调试

eg1: Refactor the file hello.py: add type hints, docstrings, and a main guard
调试结果： 模型并不会调用 todo, 尽管我在 system prompt中要求要用todo了


eg2: Create a Python package with __init__.py, utils.py, and tests/test_utils.py

实际运行结果如下，可以看出确实每一步都更新了todo


> todo:
[>] #1: Create package directory structur
[ ] #2: Create __init__.py file
[ ] #3: Create utils.py file
[ ] #4: Create tests directory and test_u

(0/4 completed)
> bash:
(no output)
> todo:
[x] #1: Create package directory structur
[>] #2: Create __init__.py file
[ ] #3: Create utils.py file
[ ] #4: Create tests directory and test_u

(1/4 completed)
> write_file:
Wrote 32 bytes to __init__.py
> todo:
[x] #1: Create package directory structure
[x] #2: Create __init__.py file
[>] #3: Create utils.py file
[ ] #4: Create tests directory and test_utils.py file

(2/4 completed)
> write_file:
Wrote 518 bytes to utils.py
> todo:
[x] #1: Create package directory structure
[x] #2: Create __init__.py file
[x] #3: Create utils.py file
[>] #4: Create tests directory and test_utils.py file

(3/4 completed)
> write_file:
Wrote 698 bytes to tests/test_utils.py
> bash:
'ls' 不是内部或外部命令，也不是可运行的程序
或批处理文件。
> bash:
驱动器 D 中的卷是 D的克隆
 卷的序列号是 E27C-140D

 D:\Professional\myCode\learnClaudeCode 的目录

2026/05/04  16:21    <DIR>          .
2026/05/04  16:21    <DIR>          ..
2026/05/04  16:16    <DIR>          -p
2026
> bash:
驱动器 D 中的卷是 D的克隆
 卷的序列号是 E27C-140D

 D:\Professional\myCode\learnClaudeCode\tests 的目录

2026/05/04  16:22    <DIR>          .
2026/05/04  16:22    <DIR>          ..
2026/05/04  16:22               723 t
> todo:
[x] #1: Create package directory structure
[x] #2: Create __init__.py file
[x] #3: Create utils.py file
[x] #4: Create tests directory and test_utils.py file

(4/4 completed)
I've successfully created a Python package with the requested structure:

1. Created `__init__.py` - This file makes the directory a Python package
2. Created `utils.py` - Contains utility functions with type hints and docstrings
3. Created `tests/` directory with `test_utils.py` - Contains unit tests for the utility functions

The package is now ready to use. You can run the tests with:
```
python -m pytest tests/
```
or
```
python tests/test_utils.py

