"""User journeys across the real DOM, HTTP routes, models, and SQLite."""

from playwright.sync_api import expect


def test_search_rate_recommend_and_watchlist(page):
    expect(page.locator("#connection")).to_contain_text("Connected")
    page.locator('.primary-nav [data-page-link="explore"]').click()
    page.locator("#movie-search").fill("Toy")
    page.locator("#movie-search").press("Enter")
    first = page.locator("#explore-results .movie-card").first
    expect(first).to_be_visible()
    movie_id = first.get_attribute("data-movie-id")
    first.locator("select").select_option("5")
    first.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator("#toast")).to_contain_text("Rating saved")
    first.locator(".poster-icon-button").click()
    page.locator('.primary-nav [data-page-link="watchlist"]').click()
    expect(page.locator("#watchlist-results .movie-card")).to_have_count(1)
    page.reload()
    page.locator('.primary-nav [data-page-link="watchlist"]').click()
    expect(page.locator("#watchlist-results .movie-card")).to_have_count(1)
    page.locator('.primary-nav [data-page-link="recommendations"]').click()
    expect(page.locator("#personal-results .movie-card").first).to_be_visible()
    expect(page.locator(f'#personal-results [data-movie-id="{movie_id}"]')).to_have_count(0)


def test_mobile_navigation_and_details(page):
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    page.locator("#mobile-menu").click()
    page.locator('.primary-nav [data-page-link="explore"]').click()
    expect(page.locator("#movie-search")).to_be_visible()
    page.locator("#movie-search").fill("Toy")
    page.locator("#movie-search").press("Enter")
    page.locator("#explore-results .movie-card").first.get_by_role("button", name="Details").click()
    expect(page.locator("#movie-dialog")).to_be_visible()
    expect(page.locator("#dialog-similar-results .movie-card").first).to_be_visible()
    page.get_by_role("button", name="Close movie details").click()
    expect(page.locator("#movie-dialog")).not_to_be_visible()


def test_story_search_filters_and_attributed_plot(page):
    page.locator('.primary-nav [data-page-link="explore"]').click()
    expect(page.locator('#discovery-mode option[value="story"]')).to_be_enabled()
    page.locator("#discovery-mode").select_option("story")
    page.locator("#max-runtime").fill("100")
    page.locator("#story-language").fill("English")
    page.locator("#movie-search").fill("a hopeful space adventure")
    page.locator("#movie-search").press("Enter")
    card = page.locator("#explore-results .movie-card").first
    expect(card).to_be_visible()
    expect(card.locator(".recommendation-reason")).to_contain_text("Story similarity")
    card.get_by_role("button", name="Details").click()
    expect(page.locator("#plot-section")).to_be_visible()
    page.locator("#plot-section summary").click()
    expect(page.locator("#movie-plot")).to_contain_text("fictional space adventure")
    expect(page.locator("#movie-metadata")).to_contain_text("95 minutes")
    expect(page.locator("#plot-license")).to_have_attribute(
        "href", "https://creativecommons.org/licenses/by-sa/3.0/us/"
    )


def test_private_profile_restore_in_a_fresh_browser_context(page, site_url):
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    card = page.locator("#home-picks .movie-card").first
    card.locator("select").select_option("5")
    card.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator("#toast")).to_contain_text("Rating saved")
    card.locator(".poster-icon-button").click()
    expect(page.locator("#watchlist-count")).to_have_text("1")
    profile = page.evaluate("JSON.parse(localStorage.getItem('cinematch.privateProfile'))")
    context = page.context.browser.new_context()
    other = context.new_page()
    try:
        other.goto(site_url)
        expect(other.locator("#home-picks .movie-card").first).to_be_visible()
        other.locator("#profile-button").click()
        other.locator("#profile-id-input").fill(f"{profile['user_id']}.{profile['token']}")
        other.locator("#profile-form").get_by_role("button", name="Restore private profile").click()
        expect(other.locator("#toast")).to_contain_text("Private profile restored")
        expect(other.locator("#watchlist-count")).to_have_text("1")
        other.locator("#profile-button").click()
        expect(other.locator("#rating-history")).to_contain_text("1 rated films")
    finally:
        context.close()
