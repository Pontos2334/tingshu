import logging

import httpx

logger = logging.getLogger("tingshu.ai")


async def generate_content(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4000,
    thinking_enabled: bool = False,
    reasoning_effort: str = "high",
) -> str:
    """调用 DeepSeek（OpenAI 兼容）API 生成内容"""
    url = f"{base_url.rstrip('/')}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "stream": False,
    }

    # 思考模式参数（DeepSeek 特有）
    if thinking_enabled:
        payload["reasoning_effort"] = reasoning_effort
        payload["extra_body"] = {"thinking": {"type": "enabled"}}

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        message = data["choices"][0]["message"]
        content = message.get("content", "")

        # 如果有思考链内容，附加到输出（可选，用于调试/展示）
        reasoning = message.get("reasoning_content")
        if reasoning:
            logger.info(f"思考链长度: {len(reasoning)} 字符")

        return content
