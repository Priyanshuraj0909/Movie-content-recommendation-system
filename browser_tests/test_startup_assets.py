"""Optional font providers must not prevent application startup."""

from playwright.sync_api import expect


def test_stalled_font_stylesheet_does_not_block_startup(page):
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    page.route("https://fonts.googleapis.com/**", lambda route: None)
    page.reload(wait_until="commit")
    expect(page.locator("#connection")).to_contain_text("Connected", timeout=5000)
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
