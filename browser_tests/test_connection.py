"""Startup failures must settle, preserve profiles, and recover without a reload."""

from playwright.sync_api import expect


def test_stalled_startup_times_out_and_retries(page):
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    original = page.evaluate("localStorage.getItem('cinematch.privateProfile')")
    page.clock.install()
    page.route("**/api/**", lambda route: None)
    page.reload(wait_until="domcontentloaded")
    page.clock.run_for(16000)
    expect(page.locator("#connection")).to_contain_text("Connection interrupted")
    expect(page.locator("#home-picks")).to_contain_text("taking too long")
    expect(page.locator("#home-picks .skeleton-row")).to_have_count(0)
    assert page.evaluate("localStorage.getItem('cinematch.privateProfile')") == original
    page.unroute("**/api/**")
    page.locator("#home-picks").get_by_role("button", name="Try again").click()
    expect(page.locator("#connection")).to_contain_text("Connected")
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    assert page.evaluate("localStorage.getItem('cinematch.privateProfile')") == original


def test_profile_error_is_not_hidden_by_healthy_api(page):
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    page.route(
        "**/api/profiles/*/ratings",
        lambda route: route.fulfill(status=503, json={"detail": "Profile storage unavailable"}),
    )
    page.reload()
    expect(page.locator("#connection")).to_contain_text("Connection interrupted")
    expect(page.locator("#home-picks")).to_contain_text("Profile storage unavailable")
    page.unroute("**/api/profiles/*/ratings")
    page.locator("#home-picks").get_by_role("button", name="Try again").click()
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    expect(page.locator("#connection")).to_contain_text("Connected")


def test_deployment_login_html_has_readable_error_and_retry(page):
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    page.route(
        "**/api/**",
        lambda route: route.fulfill(content_type="text/html", body="<html>Sign in</html>"),
    )
    page.reload()
    expect(page.locator("#home-picks")).to_contain_text("requires deployment sign-in")
    expect(page.locator("#connection")).to_contain_text("Connection interrupted")
    page.unroute("**/api/**")
    page.locator("#home-picks").get_by_role("button", name="Try again").click()
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
