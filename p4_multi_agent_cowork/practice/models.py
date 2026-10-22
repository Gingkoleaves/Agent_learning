"""统一选择离线规则模型或 DeepSeek，供 CLI 和直接运行共用。"""
import os
from pathlib import Path

from practice_common.model_adapter import DeepSeekAdapter, load_deepseek_key
from practice_common.runtime import ROOT, load_json
from .offline import OfflineModel

HERE = Path(__file__).resolve().parent


def resolve_provider(provider=None, config=None):
    """显式参数 > VS Code 已有的环境变量 > 本章配置。"""
    config = config if config is not None else load_json(HERE / "config.json")
    return provider or os.environ.get("MODEL_PROVIDER") or config.get("provider", "offline")


def make_model(provider=None, config=None):
    config = config if config is not None else load_json(HERE / "config.json")
    provider = resolve_provider(provider, config)
    if provider in ("offline", "scripted"):
        return OfflineModel()
    if provider != "deepseek":
        raise ValueError(f"未知 provider：{provider}")
    key = load_deepseek_key(ROOT)
    if not key:
        raise ValueError("请在仓库根目录 api-key.txt 填写 DeepSeek 密钥")
    return DeepSeekAdapter(key, max_calls=config["max_model_calls"],
                           timeout_seconds=config["timeout_seconds"], max_output_tokens=900)


