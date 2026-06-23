"""Web 路由测试 — FastAPI TestClient。"""

import pytest
from fastapi.testclient import TestClient
from auto_qc.web.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


class TestRoot:
    def test_root_redirects_to_qc(self, client):
        """GET / → 302/307 重定向到 /qc/"""
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers.get("location", "").rstrip("/") == "/qc"


class TestQcRoutes:
    def test_qc_page(self, client):
        resp = client.get("/qc/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_qc_history(self, client):
        resp = client.get("/qc/history")
        assert resp.status_code == 200

    def test_qc_history_with_trailing_slash(self, client):
        resp = client.get("/qc/history/")
        assert resp.status_code == 200

    def test_qc_progress_not_found(self, client):
        resp = client.get("/qc/progress/nonexistent")
        assert resp.status_code == 200
        assert "任务不存在" in resp.text

    def test_qc_result_not_found(self, client):
        resp = client.get("/qc/result/nonexistent")
        assert resp.status_code == 200
        assert "结果文件不存在" in resp.text or "不存在" in resp.text

    def test_qc_logs_not_found(self, client):
        resp = client.get("/qc/logs/nonexistent")
        assert resp.status_code == 200

    def test_qc_download_not_found(self, client):
        resp = client.get("/qc/download/nonexistent")
        assert resp.status_code == 200
        assert "不存在" in resp.text


class TestPiRoutes:
    def test_pi_page(self, client):
        resp = client.get("/pi/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_pi_history(self, client):
        resp = client.get("/pi/history")
        assert resp.status_code == 200

    def test_pi_progress_not_found(self, client):
        resp = client.get("/pi/progress/nonexistent")
        assert resp.status_code == 200
        assert "任务不存在" in resp.text

    def test_pi_result_not_found(self, client):
        resp = client.get("/pi/result/nonexistent")
        assert resp.status_code == 200
        assert "结果文件不存在" in resp.text or "不存在" in resp.text

    def test_pi_logs_not_found(self, client):
        resp = client.get("/pi/logs/nonexistent")
        assert resp.status_code == 200

    def test_pi_download_not_found(self, client):
        resp = client.get("/pi/download/nonexistent")
        assert resp.status_code == 200


class TestConfigRoutes:
    def test_config_page(self, client):
        resp = client.get("/config/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_config_save_llm_redirects(self, client, tmp_path):
        """POST /config/save-llm → 303 重定向到 /config。"""
        from auto_qc.core import config as cfg_module

        env_path = tmp_path / ".env"
        orig = cfg_module._find_env_path
        cfg_module._find_env_path = lambda: env_path

        try:
            resp = client.post("/config/save-llm", data={
                "base_url": "https://api.test.com",
                "api_key": "sk-test-key-123",
                "model": "test-model",
            }, follow_redirects=False)
            assert resp.status_code in (302, 303)
            assert "/config" in resp.headers.get("location", "")

            # 验证写入
            assert env_path.exists()
            content = env_path.read_text(encoding="utf-8")
            assert "sk-test-key-123" in content
            assert "test-model" in content
        finally:
            cfg_module._find_env_path = orig

    def test_config_save_llm_preserves_masked_key(self, client, tmp_path):
        """提交掩码后的 key（以 **** 开头）应保留原有值。"""
        from auto_qc.core import config as cfg_module

        env_path = tmp_path / ".env"
        env_path.write_text(
            "LLM_API_KEY=sk-real-key\nLLM_BASE_URL=\nLLM_MODEL=\n",
            encoding="utf-8",
        )
        orig = cfg_module._find_env_path
        cfg_module._find_env_path = lambda: env_path

        try:
            resp = client.post("/config/save-llm", data={
                "base_url": "https://other.com",
                "api_key": "****Key",  # 掩码 key
                "model": "other-model",
            }, follow_redirects=False)
            assert resp.status_code in (302, 303)

            content = env_path.read_text(encoding="utf-8")
            # 真实的 key 保留
            assert "sk-real-key" in content
        finally:
            cfg_module._find_env_path = orig
