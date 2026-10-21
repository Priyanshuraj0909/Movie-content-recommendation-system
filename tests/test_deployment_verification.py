import httpx
import pytest

from scripts.verify_deployment import verify


def test_login_page_is_not_reported_as_healthy() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, text="Protected by Vercel Authentication", headers={"content-type": "text/html"}
        )
    )
    with httpx.Client(base_url="https://example.test", transport=transport) as client:
        with pytest.raises(ValueError, match="deployment authentication"):
            verify(client)


def test_api_failure_is_not_reported_as_success() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    with httpx.Client(base_url="https://example.test", transport=transport) as client:
        with pytest.raises(ValueError, match="expected 200, got 503"):
            verify(client)
