"""测试配置加载模块"""

from __future__ import annotations

import os

from src.config import get, load_config


class TestLoadConfig:
    """配置加载基础测试"""

    def test_load_returns_dict(self, config):
        assert isinstance(config, dict)

    def test_has_required_sections(self, config):
        for section in ("news", "llm", "filters", "market", "trading", "notification", "scheduler", "logging"):
            assert section in config, f"缺少配置段: {section}"

    def test_news_sources_config(self, config):
        news = config["news"]
        assert news["jin10"]["enabled"] is False, "金十已停服，应为 disabled"
        assert news["sina"]["enabled"] is True
        assert news["eastmoney"]["enabled"] is True
        assert news["sina"]["max_items"] == 20

    def test_llm_providers_structure(self, config):
        llm = config["llm"]
        assert "active_provider" in llm
        assert "providers" in llm
        assert "bailian" in llm["providers"]
        assert "zhipu" in llm["providers"]

    def test_filters_have_enabled_flag(self, config):
        for name, f_cfg in config["filters"].items():
            assert "enabled" in f_cfg, f"筛选器 {name} 缺少 enabled 字段"


class TestEnvResolve:
    """环境变量替换测试"""

    def test_env_var_resolved(self, monkeypatch):
        monkeypatch.setenv("BAILIAN_API_KEY", "test-key-123")
        cfg = load_config(force_reload=True)
        assert cfg["llm"]["providers"]["bailian"]["api_key"] == "test-key-123"

    def test_unset_env_keeps_placeholder(self):
        monkeypatch_key = "BAILIAN_API_KEY"
        os.environ.pop(monkeypatch_key, None)
        cfg = load_config(force_reload=True)
        assert cfg["llm"]["providers"]["bailian"]["api_key"] == "${BAILIAN_API_KEY}"


class TestGetHelper:
    """get() 便捷函数测试"""

    def test_get_section(self):
        news = get("news")
        assert isinstance(news, dict)
        assert "jin10" in news

    def test_get_key(self):
        active = get("llm", "active_provider")
        assert active == "bailian"

    def test_get_default(self):
        val = get("nonexistent", "key", default="fallback")
        assert val == "fallback"
