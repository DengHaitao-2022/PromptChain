import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.errors.codes import COMMON_NOT_FOUND, INFRA_DATABASE_ERROR
from core.errors.context import REQUEST_ID_HEADER
from core.errors.exceptions import DomainError, InfrastructureError
from core.errors.handlers import install_error_infrastructure
from core.errors.mapping import map_exception
from core.errors.models import ErrorEnvelope


def _load_result_class():
    result_path = Path(__file__).resolve().parents[1] / "models" / "result.py"
    spec = spec_from_file_location("result_module_for_test", result_path)
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.Result


def test_install_error_infrastructure_returns_unified_domain_error_envelope():
    application = FastAPI()
    install_error_infrastructure(application)

    @application.get("/_tests/domain-error")
    async def _raise_domain_error():
        raise DomainError(code=COMMON_NOT_FOUND, message="工作流不存在")

    client = TestClient(application)
    response = client.get(
        "/_tests/domain-error",
        headers={REQUEST_ID_HEADER: "req-domain-001"},
    )

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == "req-domain-001"
    assert response.json() == {
        "success": False,
        "code": COMMON_NOT_FOUND,
        "message": "工作流不存在",
        "request_id": "req-domain-001",
        "details": None,
        "data": None,
    }


def test_map_exception_redacts_infrastructure_error_details():
    mapped = map_exception(
        InfrastructureError(
            code=INFRA_DATABASE_ERROR,
            message="数据库连接失败",
            details={
                "service": "postgres",
                "operation": "connect",
                "dsn": "postgresql://secret",
                "raw_error": "password authentication failed",
            },
            cause=RuntimeError("password authentication failed"),
        ),
        request_id="req-infra-001",
        path="/api/workflow/start",
        method="POST",
    )

    assert mapped.http_status == 503
    assert mapped.envelope.code == INFRA_DATABASE_ERROR
    assert mapped.envelope.message == "数据库暂时不可用，请稍后重试"
    assert mapped.envelope.details == {
        "service": "postgres",
        "operation": "connect",
    }
    assert mapped.context.internal_cause == "password authentication failed"


def test_result_keeps_legacy_shape_as_error_compatibility_layer():
    result_class = _load_result_class()
    error = ErrorEnvelope(
        code=COMMON_NOT_FOUND,
        message="资源不存在",
        request_id="req-legacy-001",
    )

    result = result_class.from_error_envelope(error)

    assert result.code == 40400
    assert result.message == "资源不存在"
    assert result.data is None


def test_app_factory_wires_global_error_infrastructure():
    app_source = Path(__file__).resolve().parents[1].joinpath("app.py").read_text()

    assert "install_error_infrastructure(application)" in app_source
