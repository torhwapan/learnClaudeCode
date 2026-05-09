
# 导入阿里云百炼大模型 SDK,DashScope（阿里百炼）的调用方式与 Anthropic 不同
from asyncio import run
from urllib import response
from pathlib import Path
import time
import dashscope
import json
from dashscope import Generation
import re;
import os;
import subprocess;
import yaml;

WORKDIR = Path.cwd()
SYSTEM = f"You are a coding agent at {WORKDIR}. Use tools to solve tasks."
KEEP_RECENT = 3
PRESERVE_RESULT_TOOLS = {"read_file"}
THRESHOLD = 50000
TRANSCRIPT_DIR = WORKDIR / ".transcripts"


# api_key
dashscope.api_key ='sk-2e071a49d12f41b88bb7d9fd7cf5a436'
# 模型名称
MODEL = "qwen3-max" 
TASKS_DIR = WORKDIR / ".tasks"

SYSTEM = f"You are a coding agent at {WORKDIR}. Use task tools to plan and track work."


# -- TaskManager: CRUD with dependency graph, persisted as JSON files --
class TaskManager:
    def __init__(self, tasks_dir: Path):
        self.dir = tasks_dir
        self.dir.mkdir(exist_ok=True)
        self._next_id = self._max_id() + 1

    def _max_id(self) -> int:
        ids = [int(f.stem.split("_")[1]) for f in self.dir.glob("task_*.json")]
        return max(ids) if ids else 0

    def _load(self, task_id: int) -> dict:
        path = self.dir / f"task_{task_id}.json"
        if not path.exists():
            raise ValueError(f"Task {task_id} not found")
        return json.loads(path.read_text())

    def _save(self, task: dict):
        path = self.dir / f"task_{task['id']}.json"
        path.write_text(json.dumps(task, indent=2, ensure_ascii=False))

    def create(self, subject: str, description: str = "") -> str:
        task = {
            "id": self._next_id, "subject": subject, "description": description,
            "status": "pending", "blockedBy": [], "owner": "",
        }
        self._save(task)
        self._next_id += 1
        return json.dumps(task, indent=2, ensure_ascii=False)

    def get(self, task_id: int) -> str:
        return json.dumps(self._load(task_id), indent=2, ensure_ascii=False)

    def update(self, task_id: int, status: str = None,
               add_blocked_by: list = None, remove_blocked_by: list = None) -> str:
        task = self._load(task_id)
        if status:
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Invalid status: {status}")
            task["status"] = status
            if status == "completed":
                self._clear_dependency(task_id)
        if add_blocked_by:
            task["blockedBy"] = list(set(task["blockedBy"] + add_blocked_by))
        if remove_blocked_by:
            task["blockedBy"] = [x for x in task["blockedBy"] if x not in remove_blocked_by]
        self._save(task)
        return json.dumps(task, indent=2, ensure_ascii=False)

    def _clear_dependency(self, completed_id: int):
        """Remove completed_id from all other tasks' blockedBy lists."""
        for f in self.dir.glob("task_*.json"):
            task = json.loads(f.read_text())
            if completed_id in task.get("blockedBy", []):
                task["blockedBy"].remove(completed_id)
                self._save(task)

    def list_all(self) -> str:
        tasks = []
        files = sorted(
            self.dir.glob("task_*.json"),
            key=lambda f: int(f.stem.split("_")[1])
        )
        for f in files:
            tasks.append(json.loads(f.read_text()))
        if not tasks:
            return "No tasks."
        lines = []
        for t in tasks:
            marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(t["status"], "[?]")
            blocked = f" (blocked by: {t['blockedBy']})" if t.get("blockedBy") else ""
            lines.append(f"{marker} #{t['id']}: {t['subject']}{blocked}")
        return "\n".join(lines)


TASKS = TaskManager(TASKS_DIR)

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
        out = ((r.stdout or "") + (r.stderr or "")).strip()
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
    "task_create": lambda **kw: TASKS.create(kw["subject"]),
    "task_update": lambda **kw: TASKS.update(kw["task_id"], kw.get("status")),
    "task_list":   lambda **kw: TASKS.list_all(),
    "task_get":    lambda **kw: TASKS.get(kw["task_id"]),
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
            "name": "load_skill",
            "description": "Load specialized knowledge by name.",
            "parameters":  {"type": "object", "properties": {"name": {"type": "string", "description": "Skill name to load"}},
                "required": ["name"]
            }
        }
    },
    {
    "type": "function",
    "function": {
      "name": "task_create",
      "description": "Create a new task.",
      "parameters": {
        "type": "object",
        "properties": {
          "subject": {
            "type": "string"
          },
          "description": {
            "type": "string"
          }
        },
        "required": ["subject"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "task_update",
      "description": "Update a task's status or dependencies.",
      "parameters": {
        "type": "object",
        "properties": {
          "task_id": {
            "type": "integer"
          },
          "status": {
            "type": "string",
            "enum": ["pending", "in_progress", "completed"]
          },
          "addBlockedBy": {
            "type": "array",
            "items": {
              "type": "integer"
            }
          },
          "removeBlockedBy": {
            "type": "array",
            "items": {
              "type": "integer"
            }
          }
        },
        "required": ["task_id"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "task_list",
      "description": "List all tasks with status summary.",
      "parameters": {
        "type": "object",
        "properties": {}
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "task_get",
      "description": "Get full details of a task by ID.",
      "parameters": {
        "type": "object",
        "properties": {
          "task_id": {
            "type": "integer"
          }
        },
        "required": ["task_id"]
      }
    }
  }
    
]


def agent_loop(messages:list):

   # 1. 确保 system 提示在消息列表的最前面。 DashScope System消息是放在messages里的
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM})

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
