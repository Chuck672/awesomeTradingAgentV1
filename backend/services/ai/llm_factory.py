import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
load_dotenv(os.path.join(_repo_root, "siliconflow_api.env"))

_base_url = os.getenv("Base_URL")
_model_name = os.getenv("Model")
_api_key = os.getenv("API_Key")


def get_llm(role: str, configs: dict | None = None) -> ChatOpenAI:
    configs = configs or {}
    role_config = configs.get(role, {}) if isinstance(configs, dict) else {}

    req_base_url = role_config.get("base_url") or _base_url or "https://api.siliconflow.cn/v1"
    req_model = role_config.get("model") or _model_name or "Qwen/Qwen2.5-7B-Instruct"
    req_api_key = role_config.get("api_key") or _api_key or "sk-dummy"

    return ChatOpenAI(
        model=req_model,
        openai_api_key=req_api_key,
        openai_api_base=req_base_url,
        max_tokens=2048,
    )

