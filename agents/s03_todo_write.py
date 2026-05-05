
# 导入阿里云百炼大模型 SDK,DashScope（阿里百炼）的调用方式与 Anthropic 不同
from asyncio import run
from urllib import response
from pathlib import Path

import dashscope
import json
from dashscope import Generation

import os;
import subprocess


WORKDIR = Path.cwd()


# api_key
dashscope.api_key ='sk-2e071a49d12f41b88bb7d9fd7cf5a436'
# 模型名称
MODEL = "qwen3-max" 

# SYSTEM提示更改，很关键
SYSTEM = f"""You are a coding agent at {WORKDIR}.
Use the todo tool to plan multi-step tasks. Mark in_progress before starting, completed when done.
Prefer tools over prose."""



class TodoManager:
    def __init__(self):
        self.items = []

    def update(self, items: list) -> str:
        if len(items) > 20:
            raise ValueError("Max 20 todos allowed")
        validated = []
        in_progress_count = 0
        for i, item in enumerate(items):
            text = str(item.get("text", "")).strip()
            status = str(item.get("status", "pending")).lower()
            item_id = str(item.get("id", str(i + 1)))
            if not text:
                raise ValueError(f"Item {item_id}: text required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {item_id}: invalid status '{status}'")
            if status == "in_progress":
                in_progress_count += 1
            validated.append({"id": item_id, "text": text, "status": status})
        if in_progress_count > 1:
            raise ValueError("Only one task can be in_progress at a time")
        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "No todos."
        lines = []
        for item in self.items:
            marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}[item["status"]]
            lines.append(f"{marker} #{item['id']}: {item['text']}")
        done = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({done}/{len(self.items)} completed)")
        return "\n".join(lines)

TODO = TodoManager()





# 定义函数

# 使用 / 拼接相对路径，防止用户访问工作目录之外的文件。
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


def run_read(path: str, limit: int = None) -> str:
    try:
        text = safe_path(path).read_text()
        lines = text.splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


# -- The dispatch map: {tool_name: handler} --
TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "todo":       lambda **kw: TODO.update(kw["items"]),
}



# 阿里百炼的 TOOLS 的定义也不一样
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace exact text in file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"}
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "todo",
            "description": "Update task list. Track progress on multi-step tasks.",
            "parameters": {
                "type": "object",
                "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}, "required": ["id", "text", "status"]}}},
                "required": ["items"]
            }
        }
    }
]


def agent_loop(messages:list):

   # 1. 确保 system 提示在消息列表的最前面。 DashScope System消息是放在messages里的
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM})

    rounds_since_todo = 0

    while True:
        response = Generation.call(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            result_format='message',  # 阿里云百炼必须加这个参数才能拿到结构化消息
            incremental_output=False
            # max_tokens=8000
        )
        if response.status_code != 200:
            print(f"API Error: {response.code} - {response.message}")
            return
        # 3. 解析响应 (DashScope 结构与 Anthropic 不同)
        msg = response.output.choices[0].message

        # Append assistant turn
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.get('tool_calls')})
         # 检查是否有工具调用
        if not msg.get('tool_calls'):
            return # 没有工具调用，说明对话结束
        # 4. 执行工具调用
        results = []
        used_todo = False
        # 4. 执行工具调用
        for tc in msg.get('tool_calls'):
            func_name = tc["function"]["name"]
            func_args_str = tc["function"]["arguments"]
            
            if isinstance(func_args_str, str):
                func_args = json.loads(func_args_str)
            else:
                func_args = func_args_str
            handler = TOOL_HANDLERS.get(func_name)
            output = handler(**func_args) if handler else f"Unknown tool: {func_name}"
            print(f"> {func_name}:")
            print(output[:200])
            
            # 【修改】阿里百炼要求每个 tool 结果作为独立的消息追加，且字段名为 tool_call_id
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"], 
                "content": output
            })

            if func_name == "todo":
                used_todo = True

        rounds_since_todo = 0 if used_todo else rounds_since_todo + 1
        # 超过3轮未更新todo，追加一条用户提醒消息
        if rounds_since_todo >= 3:
            messages.append({"role": "user", "content": "<reminder>Update your todos.</reminder>"}) 

# 主函数，程序入口
if  __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[32m>>> \033[0m") #获取用户输入
        except(EOFError, KeyboardInterrupt):
            break
        #用户输入 q,exit或者回车时，退出程序
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
# 打印最后一条回复
        last_msg = history[-1]
        if last_msg["role"] == "assistant":
            print(last_msg["content"])
        print()
