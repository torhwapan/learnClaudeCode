
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
def estimate_tokens(messages: list) -> int:
    """Rough token count: ~4 chars per token."""
    return len(str(messages)) // 4


# -- Layer 1: micro_compact - replace old tool results with placeholders --
def micro_compact(messages: list) -> list:
    # DashScope 格式：tool 结果是 role="tool" 的独立消息
    tool_results = []
    for msg_idx, msg in enumerate(messages):
        if msg["role"] == "tool":
            tool_results.append((msg_idx, msg))
            
    if len(tool_results) <= KEEP_RECENT:
        return messages
        
    # 构建 tool_call_id -> tool_name 的映射（DashScope 格式）
    tool_name_map = {}
    for msg in messages:
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tool_name_map[tc["id"]] = tc["function"]["name"]
                
    # 保留最近 KEEP_RECENT 个工具结果，压缩更早的
    to_clear = tool_results[:-KEEP_RECENT]
    for _, result in to_clear:
        content = result.get("content", "")
        if not isinstance(content, str) or len(content) <= 100:
            continue
        tool_id = result.get("tool_call_id", "")
        tool_name = tool_name_map.get(tool_id, "unknown_tool")
        if tool_name in PRESERVE_RESULT_TOOLS:
            continue
        result["content"] = f"[Previous: used {tool_name}]"
    return messages


# -- Layer 2: auto_compact - save transcript, summarize, replace messages --
def auto_compact(messages: list) -> list:
    # Save full transcript to disk
    TRANSCRIPT_DIR.mkdir(exist_ok=True)
    transcript_path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    with open(transcript_path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    print(f"[transcript saved: {transcript_path}]")
    # Ask LLM to summarize using DashScope Generation.call
    conversation_text = json.dumps(messages, default=str)[-80000:]
    summary_response = Generation.call(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": (
                "Summarize this conversation for continuity. Include: "
                "1) What was accomplished, 2) Current state, 3) Key decisions made. "
                "Be concise but preserve critical details.\n\n" + conversation_text
            )
        }],
        result_format='message',
    )
    # 解析摘要响应 (DashScope 格式)
    summary = ""
    if summary_response.status_code == 200:
        summary = summary_response.output.choices[0].message.content
    if not summary:
        summary = "No summary generated."
    # Replace all messages with compressed summary
    return [
        {"role": "user", "content": f"[Conversation compressed. Transcript: {transcript_path}]\n\n{summary}"},
    ]








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
    }
]


def agent_loop(messages:list):

   # 1. 确保 system 提示在消息列表的最前面。 DashScope System消息是放在messages里的
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM})

    while True:

                # Layer 1: micro_compact before each LLM call
        micro_compact(messages)
        # Layer 2: auto_compact if token estimate exceeds threshold
        if estimate_tokens(messages) > THRESHOLD:
            print("[auto_compact triggered]")
            messages[:] = auto_compact(messages)    

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
        manual_compact = False
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

                    # Layer 3: manual compact triggered by the compact tool
            if manual_compact:
                print("[manual compact]")
                messages[:] = auto_compact(messages)
                return

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
