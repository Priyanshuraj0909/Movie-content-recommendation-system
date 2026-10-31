import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect


def test_five_film_onboarding_and_editable_library(page):
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    page.locator('.primary-nav [data-page-link="recommendations"]').click()
    page.locator("#page-recommendations [data-start-onboarding]").click()
    expect(page.locator("#onboarding-dialog")).to_be_visible()
    for count in range(1, 6):
        row = page.locator("#onboarding-results .taste-entry").first
        expect(row).to_be_visible()
        mid = row.get_attribute("data-movie-id")
        row.locator("select").select_option("5")
        row.get_by_role("button", name="Save", exact=True).click()
        expect(page.locator("#onboarding-progress-label")).to_have_text(f"{count} of 5 films rated")
        expect(page.locator(f'#onboarding-results [data-movie-id="{mid}"]')).to_have_count(0)
    page.locator("#finish-onboarding").click()
    expect(page.locator("#onboarding-dialog")).not_to_be_visible()
    with page.expect_response(lambda response: "mode=discovery" in response.url):
        page.locator('[data-pick-mode="discovery"]').click()
    expect(page.locator('[data-pick-mode="discovery"]')).to_have_attribute("aria-pressed", "true")
    page.locator('.primary-nav [data-page-link="library"]').click()
    expect(page.locator("#library-summary")).to_contain_text("5 rated")
    expect(page.locator("#library-more")).not_to_be_visible()
    entry = page.locator("#library-results .taste-entry").first
    mid = entry.get_attribute("data-movie-id")
    entry.locator("select").select_option("3.5")
    entry.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator(f'#library-results [data-movie-id="{mid}"]')).to_contain_text("3.5 ★")
    expect(page.locator("#library-summary")).to_contain_text("5 rated")


def test_explicit_watched_and_dismissed_feedback_can_be_undone(page):
    card = page.locator("#home-picks .movie-card").first
    expect(card).to_be_visible()
    mid = card.get_attribute("data-movie-id")
    card.get_by_role("button", name="Mark ", exact=False).click()
    expect(page.locator("#toast")).to_contain_text("Marked watched")
    page.locator('.primary-nav [data-page-link="library"]').click()
    expect(page.locator("#library-summary")).to_contain_text("0 rated · 1 marked watched")
    page.locator("#library-filter").select_option("watched")
    entry = page.locator(f'#library-results [data-movie-id="{mid}"]')
    expect(entry).to_be_visible()
    entry.get_by_role("button", name="Undo feedback", exact=False).click()
    expect(page.locator("#library-results .taste-entry")).to_have_count(0)
    page.locator('.primary-nav [data-page-link="recommendations"]').click()
    card = page.locator(f'#personal-results [data-movie-id="{mid}"]')
    expect(card).to_be_visible()
    card.get_by_role("button", name="Not interested in", exact=False).click()
    expect(page.locator("#toast")).to_contain_text("stay out of your picks")
    page.locator('.primary-nav [data-page-link="library"]').click()
    page.locator("#library-filter").select_option("not_interested")
    expect(page.locator(f'#library-results [data-movie-id="{mid}"]')).to_be_visible()
    expect(page.locator("#library-summary")).to_contain_text("0 rated")


def test_failed_profile_restore_preserves_active_identity_and_cache(page, site_url):
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    previous = page.evaluate("JSON.parse(localStorage.getItem('cinematch.privateProfile')).user_id")
    candidate = page.request.post(site_url + "/api/profiles").json()
    path = f"**/api/profiles/{candidate['user_id']}/watchlist"
    page.route(
        path, lambda route: route.fulfill(status=503, json={"detail": "Temporarily unavailable"})
    )
    page.locator("#profile-button").click()
    page.locator("#profile-id-input").fill(f"{candidate['user_id']}.{candidate['token']}")
    page.locator("#profile-form").get_by_role("button", name="Restore private profile").click()
    expect(page.locator("#toast")).to_contain_text("Temporarily unavailable")
    assert (
        page.evaluate("JSON.parse(localStorage.getItem('cinematch.privateProfile')).user_id")
        == previous
    )
    page.reload()
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    assert (
        page.evaluate("JSON.parse(localStorage.getItem('cinematch.privateProfile')).user_id")
        == previous
    )


def test_legacy_watchlist_import_does_not_resurrect_removed_entries(page):
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    page.evaluate("""() => {
      const movie = { movie_id: 1, title: 'Toy Space Adventure 1 (2000)',
        genres: 'Adventure|Sci-Fi' };
      localStorage.setItem('cinematch.watchlist', JSON.stringify([movie]));
      localStorage.removeItem('cinematch.watchlistImportSaved');
    }""")
    page.reload()
    expect(page.locator("#watchlist-count")).to_have_text("1")
    page.locator('.primary-nav [data-page-link="watchlist"]').click()
    page.locator("#watchlist-results .poster-icon-button").click()
    expect(page.locator("#watchlist-count")).to_have_text("0")
    page.reload()
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    expect(page.locator("#watchlist-count")).to_have_text("0")
    assert page.evaluate("JSON.parse(localStorage.getItem('cinematch.watchlist')).length") == 1


def test_public_ratings_requests_are_batched_for_large_lists(page):
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    batches = []

    def respond(route):
        ids = [int(value) for value in parse_qs(urlparse(route.request.url).query)["movie_ids"]]
        if min(ids) >= 1000:
            batches.append(len(ids))
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([{"movie_id": mid, "tmdb": {}, "imdb": {}} for mid in ids]),
        )

    page.route("**/api/movies/external-ratings?*", respond)
    page.evaluate("""() => renderMovies(document.querySelector('#explore-results'),
      Array.from({length: 65}, (_, i) => ({movie_id: 1000 + i,
        title: 'Fixture ' + i, genres: 'Drama'})), '', '')""")
    page.wait_for_function("externalRatings.has(1064)")
    assert batches == [30, 30, 5]


def test_slow_old_recommendations_cannot_replace_the_selected_discovery_mode(page):
    expect(page.locator("#home-picks .movie-card").first).to_be_visible()
    pending = []

    def respond(route):
        if "mode=balanced" in route.request.url:
            pending.append(route)
        else:
            route.fulfill(
                status=200,
                json=[
                    {
                        "movie_id": 12,
                        "title": "Discovery choice",
                        "genres": "Adventure",
                        "score": 0.8,
                    }
                ],
            )

    page.route("**/api/recommendations/users/*", respond)
    page.locator('.primary-nav [data-page-link="recommendations"]').click()
    page.locator('[data-pick-mode="discovery"]').click()
    expect(page.locator("#personal-results .movie-title")).to_have_text("Discovery choice")
    assert pending
    # Finish the older response after discovery has already rendered.
    pending[0].fulfill(
        status=200,
        json=[
            {
                "movie_id": 11,
                "title": "Older balanced choice",
                "genres": "Drama",
                "score": 0.9,
            }
        ],
    )
    page.evaluate(
        "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    expect(page.locator("#personal-results .movie-title")).to_have_text("Discovery choice")
