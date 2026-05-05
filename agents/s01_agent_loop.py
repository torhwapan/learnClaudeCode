
# 导入阿里云百炼大模型 SDK,DashScope（阿里百炼）的调用方式与 Anthropic 不同
from asyncio import run
from urllib import response

import dashscope
import json
from dashscope import Generation

import os;
import subprocess

# api_key
dashscope.api_key ='sk-2e071a49d12f41b88bb7d9fd7cf5a436'
# 模型名称
MODEL = "qwen3-max" 
SYSTEM = f"You are a coding agent at {os.getcwd()}. Use bash to solve tasks. Act, don't explain."

# 阿里百炼的 TOOLS 的定义也不一样
TOOLS = [{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command",
        "parameters": {  # 不是 input_schema
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                }
            },
            "required": ["command"],
        }
    }
}]



def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        # subprocess 是 Python 的内置标准库，用于在 Python 代码中调用外部程序/命令。
        r = subprocess.run(command, shell=True, cwd = os.getcwd(),capture_output=True, text=True,timeout = 120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "no output"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out(120s)"
    except(FileNotFoundError, OSError) as e:
        return f"Error: {str(e)}"





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
        for tc in msg.get('tool_calls'):
            # 1. 使用字典方式访问数据
            func_name = tc["function"]["name"]
            # 2. arguments 已经是字典或字符串，视模型而定，通常建议先判断
            func_args_str = tc["function"]["arguments"]
            if isinstance(func_args_str, str):
                func_args = json.loads(func_args_str)
            else:
                func_args = func_args_str
            if func_name == "bash":
                print(f"\033[33m$ {func_args['command']}\033[0m")
                output = run_bash(func_args['command'])
                print(output[:200])
                
                # DashScope 要求 result 格式
                # ！！！！！！！！！！！！！！！！！！！！  注意： DashScope对工具的调用结果，要求其role必须为tool。
                results.append({
                    "role": "tool",
                    "content": output,
                    "tool_call_id": tc["id"]
                })
        
        messages.extend(results)
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
