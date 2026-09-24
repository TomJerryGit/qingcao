# -*- coding: utf-8 -*-
"""重构会话（多轮 AI 对话）"""
import time
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum, auto


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    code_snapshot: str = ""  # 消息关联的代码快照


@dataclass
class RefactorIteration:
    """一次迭代"""
    iteration: int = 0
    original_code: str = ""
    proposed_code: str = ""
    user_request: str = ""
    ai_explanation: str = ""
    accepted: bool = False
    timestamp: float = field(default_factory=time.time)


class RefactorSession:
    """重构会话"""

    def __init__(self, ai_client, original_code: str,
                 language: str = "python"):
        self.session_id = uuid.uuid4().hex[:8]
        self.ai_client = ai_client
        self.original_code = original_code
        self.current_code = original_code
        self.language = language
        self.messages: List[Message] = []
        self.iterations: List[RefactorIteration] = []

        # 初始化系统提示
        self.system_prompt = (
            "你是一个资深的代码重构助手。用户会选中一段代码，"
            "然后提出修改需求。请：\n"
            "1. 理解用户的真实意图\n"
            "2. 输出重构后的**完整代码**（放在 ``` 代码块中）\n"
            "3. 简要说明改了什么\n"
            "4. 保持代码功能不变，只改进可读性/性能/可维护性\n"
            "5. 使用 %s 语言" % language
        )

        # 添加初始消息
        self.messages.append(Message(
            role="user",
            content="这是待重构的代码：\n```%s\n%s\n```" % (
                language, original_code
            )
        ))

    def send_request(self, user_request: str,
                     callback=None, error_callback=None):
        """发送用户请求（异步）"""
        self.messages.append(Message(
            role="user",
            content=user_request,
            code_snapshot=self.current_code,
        ))

        # 异步调用 AI
        import threading
        def worker():
            try:
                # 构建消息列表
                api_messages = []
                for msg in self.messages:
                    api_messages.append({
                        "role": msg.role,
                        "content": msg.content,
                    })

                # 调用 AI（非流式，便于解析完整输出）
                result = self.ai_client._chat(
                    api_messages, self.system_prompt
                )

                # 解析代码块
                proposed, explanation = self._parse_response(result)

                # 记录
                iteration = RefactorIteration(
                    iteration=len(self.iterations) + 1,
                    original_code=self.current_code,
                    proposed_code=proposed,
                    user_request=user_request,
                    ai_explanation=explanation,
                )
                self.iterations.append(iteration)

                self.messages.append(Message(
                    role="assistant",
                    content=result,
                ))

                if callback:
                    callback(iteration)
            except Exception as e:
                if error_callback:
                    error_callback(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _parse_response(self, response: str):
        """从 AI 响应中提取代码块和说明"""
        import re

        # 提取第一个代码块
        pattern = re.compile(
            r'```(?:\w+)?\s*\n(.*?)\n```', re.DOTALL
        )
        match = pattern.search(response)

        if match:
            code = match.group(1)
            # 说明文字：代码块之后的内容
            explanation = response[match.end():].strip()
            return code, explanation

        return response, ""

    def accept_iteration(self, iteration_index: int):
        """接受某次迭代"""
        if 0 <= iteration_index < len(self.iterations):
            iter_obj = self.iterations[iteration_index]
            iter_obj.accepted = True
            self.current_code = iter_obj.proposed_code

    def get_current_code(self):
        return self.current_code

    def get_all_iterations(self):
        return list(self.iterations)

    def get_summary(self):
        """会话摘要"""
        return {
            'session_id': self.session_id,
            'original_length': len(self.original_code),
            'current_length': len(self.current_code),
            'iterations': len(self.iterations),
            'accepted': sum(1 for i in self.iterations if i.accepted),
        }