一，问题：
Agent 工作越久, messages 数组越臃肿。每次读文件、跑命令的输出都永久留在上下文里

二，解决方案：
父子Agent， 父Agent负责管理和分配任务，子Agent负责执行子任务，比如某子任务需要扫描30次(个)文件，子任务执行完成后，只返回最终的结果给父Agent，中间的查询过程messages可以丢弃掉。

三，工作原理
1,父 Agent 有一个 task 工具。Subagent 拥有除 task 外的所有基础工具 (禁止递归生成)。
2,Subagent 以 messages=[] 启动, 运行自己的循环。只有最终文本返回给父 Agent。

