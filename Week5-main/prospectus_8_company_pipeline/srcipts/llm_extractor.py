from __future__ import annotations
from typing import Any, Dict
import json
import os
import re
import requests

SYSTEM_INSTRUCTION = """
你是招股书股权演变信息抽取器。只依据给定原文抽取，不补充、不推断未披露事实。
输出必须是严格JSON对象，字段只允许包含：
capital_increase、equity_transfer、equity_snapshot。
每条记录必须保留source_page、source_text和confidence。
日期统一YYYY-MM-DD；金额和股数输出纯数字；比例输出0到100之间的数值。
无法确认的字段填null。不要输出Markdown。
"""

class LLMExtractor:
    def __init__(self, config: Dict[str, Any], schema: Dict[str, Any]):
        self.config = config
        self.schema = schema

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled") and self.config.get("endpoint"))

    def extract(self, company: Dict[str, Any], section: str, text: str) -> Dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("LLM未启用")
        api_key = os.getenv(self.config.get("api_key_env", "LLM_API_KEY"), "")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        prompt = {
            "company": company,
            "section": section,
            "json_schema": self.schema,
            "source_text": text
        }
        payload = {
            "model": self.config.get("model", ""),
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}
            ],
            "temperature": 0
        }
        response = requests.post(
            self.config["endpoint"],
            headers=headers,
            json=payload,
            timeout=int(self.config.get("timeout_seconds", 120))
        )
        response.raise_for_status()
        data = response.json()
        content = self._get_content(data)
        return self._parse_json(content)

    @staticmethod
    def _get_content(data: Dict[str, Any]) -> str:
        # 兼容常见OpenAI风格返回，也允许服务直接返回JSON对象。
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        if "output_text" in data:
            return data["output_text"]
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        content = content.strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM返回结果不是JSON对象")
        return parsed
