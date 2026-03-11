"""百炼大模型客户端 - 封装 Dashscope API 调用"""

import json
import os
import re
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()


def _get_api_key(config: Optional[dict] = None, api_key_override: Optional[str] = None) -> str:
    """获取 API 密钥：优先 api_key_override，其次 config.api.dashscope_api_key，最后环境变量"""
    if api_key_override and api_key_override.strip():
        return api_key_override.strip()
    if config:
        key = config.get("api", {}).get("dashscope_api_key") or ""
        if key and key.strip():
            return key.strip()
    key = os.getenv("DASHSCOPE_API_KEY", "")
    if not key or key == "your_api_key_here":
        raise ValueError(
            "请配置 DASHSCOPE_API_KEY：复制 .env.example 为 .env 并填入 API 密钥，"
            "或在个人中心配置百炼 API 密钥"
        )
    return key


def get_embeddings(
    texts: list[str],
    model: str = "text-embedding-v3",
    config: Optional[dict] = None,
    api_key: Optional[str] = None,
) -> list[list[float]]:
    """获取文本嵌入向量"""
    try:
        from dashscope import TextEmbedding
    except ImportError:
        raise ImportError("请安装 dashscope: pip install dashscope")

    resp = TextEmbedding.call(
        model=model,
        input=texts,
        api_key=_get_api_key(config, api_key),
    )
    if resp.status_code != 200:
        raise RuntimeError(f"嵌入 API 调用失败: {resp.message}")
    return [item["embedding"] for item in resp.output["embeddings"]]


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str = "qwen-max",
    temperature: float = 0.2,
    timeout: int = 30,
    max_retries: int = 3,
    config: Optional[dict] = None,
    api_key: Optional[str] = None,
) -> str:
    """
    调用百炼大模型进行推理。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        model: 模型名称，默认 qwen-max
        temperature: 温度参数
        timeout: 超时时间（秒）
        max_retries: 最大重试次数
        config: 配置字典，用于读取 api_key 等

    Returns:
        模型输出的原始文本

    Raises:
        RuntimeError: API 调用失败
    """
    import logging
    logger = logging.getLogger("aireview.llm")
    
    try:
        from dashscope import Generation
    except ImportError:
        raise ImportError("请安装 dashscope: pip install dashscope")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    # 打印调用大模型的输入
    logger.info("=" * 80)
    logger.info("🤖 调用大模型 API")
    logger.info(f"模型: {model}")
    logger.info(f"温度: {temperature}")
    logger.info(f"超时: {timeout}秒")
    logger.info("-" * 80)
    logger.info("📝 System Prompt:")
    logger.info(system_prompt[:500] + "..." if len(system_prompt) > 500 else system_prompt)
    logger.info("-" * 80)
    logger.info("📝 User Prompt:")
    logger.info(user_prompt[:1000] + "..." if len(user_prompt) > 1000 else user_prompt)
    logger.info("=" * 80)

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 尝试调用 (第 {attempt + 1}/{max_retries} 次)...")
            resp = Generation.call(
                model=model,
                messages=messages,
                api_key=_get_api_key(config, api_key),
                temperature=temperature,
                result_format="message",
                timeout=timeout,
            )
            if resp.status_code == 200:
                out = resp.output
                result = ""
                if hasattr(out, "choices") and out.choices:
                    result = out.choices[0].message.content
                else:
                    result = getattr(out, "text", "") or ""
                
                # 打印大模型的输出
                logger.info("=" * 80)
                logger.info("✅ 大模型返回成功")
                logger.info("-" * 80)
                logger.info("📤 Model Output:")
                logger.info(result[:2000] + "..." if len(result) > 2000 else result)
                logger.info("=" * 80)
                
                return result
            last_error = RuntimeError(f"大模型调用失败: {resp.message}")
            logger.error(f"❌ API返回错误: {resp.message}")
        except Exception as e:
            last_error = e
            logger.error(f"❌ 调用异常: {e}")
        if attempt < max_retries - 1:
            logger.warning(f"⚠️  重试中...")
            continue
        raise last_error
    raise last_error or RuntimeError("调用失败")


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    model: str = "qwen-max",
    temperature: float = 0.2,
    timeout: int = 30,
    max_retries: int = 3,
    config: Optional[dict] = None,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """
    调用大模型并解析 JSON 输出。

    Returns:
        解析后的 JSON 字典

    Raises:
        ValueError: JSON 解析失败
    """
    raw = call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
        config=config,
        api_key=api_key,
    )
    return _parse_json_from_text(raw)


def _parse_json_from_text(text: str) -> dict[str, Any]:
    """从模型输出中提取并解析 JSON"""
    text = text.strip()
    # 尝试提取 ```json ... ``` 代码块
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if json_match:
        text = json_match.group(1).strip()
    # 尝试匹配 {...}
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        text = brace_match.group(0)
    return json.loads(text)


# 兼容旧接口
def chat(
    messages: list[dict],
    model: str = "qwen-plus",
    temperature: float = 0.3,
    config: Optional[dict] = None,
    api_key: Optional[str] = None,
) -> str:
    """调用大模型进行对话（兼容旧接口）"""
    try:
        from dashscope import Generation
    except ImportError:
        raise ImportError("请安装 dashscope: pip install dashscope")

    resp = Generation.call(
        model=model,
        messages=messages,
        api_key=_get_api_key(config, api_key),
        temperature=temperature,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"大模型调用失败: {resp.message}")
    return resp.output.text
