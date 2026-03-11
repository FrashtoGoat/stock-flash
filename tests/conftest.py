"""测试公共 fixtures"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import load_config  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """每个测试前重置配置缓存，防止测试间污染"""
    import src.config as cfg_module
    cfg_module._config_cache = None
    yield
    cfg_module._config_cache = None


@pytest.fixture
def clean_news_registry():
    """提供干净的新闻源注册表（仅在需要测试注册机制时使用）"""
    import src.news.factory as nf
    saved = nf._REGISTRY.copy()
    nf._REGISTRY.clear()
    yield nf._REGISTRY
    nf._REGISTRY.clear()
    nf._REGISTRY.update(saved)


@pytest.fixture
def clean_filter_registry():
    """提供干净的筛选器注册表"""
    import src.filters.factory as ff
    saved = ff._REGISTRY.copy()
    ff._REGISTRY.clear()
    yield ff._REGISTRY
    ff._REGISTRY.clear()
    ff._REGISTRY.update(saved)


@pytest.fixture
def clean_llm_registry():
    """提供干净的 LLM Provider 注册表"""
    import src.llm_provider.factory as lf
    saved = lf._REGISTRY.copy()
    lf._REGISTRY.clear()
    yield lf._REGISTRY
    lf._REGISTRY.clear()
    lf._REGISTRY.update(saved)


@pytest.fixture
def config():
    """加载并返回配置"""
    return load_config(force_reload=True)
