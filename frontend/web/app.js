const API = "/api";
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const PALETTE = ["#6c51aa", "#8b4c75", "#375f77", "#83603e", "#514b8b", "#397061", "#8c4850", "#526483"];
const WATCHLIST_KEY = "cinematch.watchlist";
const PROFILE_KEY = "cinematch.profileId";
let profileId = readProfileId();
let currentSearchResults = [];
let activeGenre = "";
let searchTimer;
let toastTimer;
let activeMovie = null;
const externalRatings = new Map();

function readProfileId() {
  const stored = Number.parseInt(localStorage.getItem(PROFILE_KEY), 10);
  if (Number.isSafeInteger(stored) && stored > 0) return stored;
  const entropy = new Uint32Array(1);
  crypto.getRandomValues(entropy);
  const generated = 100000000 + (entropy[0] % 1800000000);
  localStorage.setItem(PROFILE_KEY, String(generated));
  return generated;
}

async function request(path, options = {}) {
  const response = await fetch(API + path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = "The cinema service returned " + response.status + ".";
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch { /* Keep the readable status message. */ }
    throw new Error(message);
  }
  return response.json();
}

function getWatchlist() {
  try {
    const value = JSON.parse(localStorage.getItem(WATCHLIST_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function saveWatchlist(items) {
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(items));
  updateWatchlistCount();
}

function updateWatchlistCount() {
  $("#watchlist-count").textContent = String(getWatchlist().length);
}

function hashTitle(title) {
  let hash = 0;
  for (let index = 0; index < title.length; index += 1) {
    hash = ((hash << 5) - hash + title.charCodeAt(index)) | 0;
  }
  return Math.abs(hash);
}

function getYear(title) {
  const match = String(title).match(/\((\d{4})\)\s*$/);
  return match ? match[1] : "";
}

function getGenres(movie) {
  return String(movie.genres || "")
    .split("|")
    .filter((genre) => genre && genre !== "(no genres listed)");
}

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 3300);
}

function showEmpty(container, title, message, isError = false) {
  container.replaceChildren();
  const panel = document.createElement("div");
  panel.className = "empty-panel" + (isError ? " error-panel" : "");
  const icon = document.createElement("span");
  icon.className = "empty-symbol";
  icon.textContent = isError ? "!" : "✧";
  const heading = document.createElement("h2");
  heading.textContent = title;
  const copy = document.createElement("p");
  copy.textContent = message;
  panel.append(icon, heading, copy);
  container.append(panel);
}

function isSaved(movieId) {
  return getWatchlist().some((movie) => Number(movie.movie_id) === Number(movieId));
}

function toggleWatchlist(movie) {
  const list = getWatchlist();
  const existing = list.findIndex((item) => Number(item.movie_id) === Number(movie.movie_id));
  if (existing >= 0) {
    list.splice(existing, 1);
    saveWatchlist(list);
    showToast("Removed from your watchlist.");
  } else {
    list.unshift({
      movie_id: Number(movie.movie_id),
      title: String(movie.title),
      genres: String(movie.genres || ""),
      score: Number.isFinite(movie.score) ? movie.score : null,
      saved_at: Date.now(),
    });
    saveWatchlist(list);
    showToast("Saved for your next movie night.");
  }
  renderWatchlist();
  if (activeMovie && Number(activeMovie.movie_id) === Number(movie.movie_id)) updateDialogWatchlistButton();
}

function makePoster(movie) {
  const poster = document.createElement("div");
  poster.className = "poster-art";
  poster.style.setProperty("--poster-color", PALETTE[hashTitle(movie.title) % PALETTE.length]);
  poster.setAttribute("role", "img");
  poster.setAttribute("aria-label", "Original CineMatch artwork for " + movie.title);

  const orbit = document.createElement("span");
  orbit.className = "poster-orbit";
  orbit.setAttribute("aria-hidden", "true");
  const number = document.createElement("span");
  number.className = "poster-number";
  number.textContent = "CINEMATCH · " + String(movie.movie_id).padStart(4, "0");
  const words = document.createElement("div");
  const title = document.createElement("h3");
  title.className = "poster-title";
  title.textContent = movie.title.replace(/\s*\(\d{4}\)\s*$/, "");
  const year = getYear(movie.title);
  if (year) {
    const yearLabel = document.createElement("p");
    yearLabel.className = "poster-year";
    yearLabel.textContent = year;
    words.append(title, yearLabel);
  } else {
    words.append(title);
  }
  poster.append(orbit, number, words);
  return poster;
}

function makeRatingControls(movie) {
  const controls = document.createElement("div");
  controls.className = "card-rating";
  const select = document.createElement("select");
  select.setAttribute("aria-label", "Your rating for " + movie.title);
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Rate it";
  placeholder.selected = true;
  select.append(placeholder);
  for (let value = 5; value >= 0.5; value -= 0.5) {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = value.toFixed(1) + " ★";
    select.append(option);
  }
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Save";
  button.addEventListener("click", async () => {
    const rating = Number(select.value);
    if (!rating) {
      showToast("Choose a rating first.", true);
      select.focus();
      return;
    }
    button.disabled = true;
    button.textContent = "…";
    try {
      await request("/ratings", {
        method: "POST",
        body: JSON.stringify({ user_id: profileId, movie_id: Number(movie.movie_id), rating }),
      });
      showToast("Rating saved. Your next picks will learn from it.");
      if ($("#page-recommendations").classList.contains("active")) loadRecommendations();
      if ($("#page-home").classList.contains("active")) loadHomePicks();
    } catch (error) {
      showToast(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = "Save";
    }
  });
  controls.append(select, button);
  return controls;
}

function makeMovieCard(movie) {
  const card = document.createElement("article");
  card.className = "movie-card";
  card.dataset.movieId = String(movie.movie_id);
  const posterWrap = document.createElement("div");
  posterWrap.className = "poster-wrap";
  const poster = makePoster(movie);
  const topActions = document.createElement("div");
  topActions.className = "poster-top-actions";
  const save = document.createElement("button");
  save.className = "poster-icon-button" + (isSaved(movie.movie_id) ? " saved" : "");
  save.type = "button";
  save.setAttribute("aria-label", (isSaved(movie.movie_id) ? "Remove " : "Add ") + movie.title + " " + (isSaved(movie.movie_id) ? "from" : "to") + " watchlist");
  save.title = isSaved(movie.movie_id) ? "Remove from watchlist" : "Add to watchlist";
  save.textContent = isSaved(movie.movie_id) ? "✓" : "＋";
  save.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleWatchlist(movie);
    const saved = isSaved(movie.movie_id);
    save.classList.toggle("saved", saved);
    save.textContent = saved ? "✓" : "＋";
    save.title = saved ? "Remove from watchlist" : "Add to watchlist";
  });
  topActions.append(save);
  posterWrap.append(poster, topActions);

  const info = document.createElement("div");
  info.className = "movie-card-info";
  const title = document.createElement("h3");
  title.className = "movie-title";
  title.textContent = movie.title;
  const genres = document.createElement("p");
  genres.className = "movie-meta";
  genres.textContent = getGenres(movie).slice(0, 3).join(" · ") || "Genre not listed";
  const ratingLine = document.createElement("div");
  ratingLine.className = "movie-public-ratings";
  ratingLine.setAttribute("aria-label", "IMDb and TMDB community ratings");
  const bottom = document.createElement("div");
  bottom.className = "movie-card-bottom";
  if (Number.isFinite(movie.score)) {
    const score = document.createElement("span");
    score.className = "movie-score";
    score.textContent = "Match " + Math.round(movie.score * 100) + "%";
    bottom.append(score);
  }
  const detail = document.createElement("button");
  detail.className = "movie-detail-link";
  detail.type = "button";
  detail.textContent = "Details";
  detail.addEventListener("click", () => openMovie(movie));
  bottom.append(detail);
  info.append(title, genres, ratingLine, bottom, makeRatingControls(movie));
  card.append(posterWrap, info);
  return card;
}

function renderMovies(container, movies, emptyTitle, emptyMessage) {
  container.replaceChildren();
  if (!movies.length) {
    showEmpty(container, emptyTitle, emptyMessage);
    return;
  }
  movies.forEach((movie) => container.append(makeMovieCard(movie)));
  loadCardRatings(container, movies);
}

function formatVotes(value) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString() + " votes" : "";
}

function ratingLabel(source, rating) {
  if (!rating || rating.rating === null || rating.rating === undefined || !Number.isFinite(Number(rating.rating))) return "";
  const score = Number(rating.rating).toFixed(1);
  const votes = formatVotes(rating.vote_count);
  return "★ " + source + " " + score + "/10" + (votes ? " · " + votes : "");
}

function renderCardRating(container, movieId, data) {
  $$('[data-movie-id="' + Number(movieId) + '"] .movie-public-ratings', container).forEach((line) => {
    line.replaceChildren();
    [["IMDb", data.imdb], ["TMDB", data.tmdb]].forEach(([source, rating]) => {
      const label = ratingLabel(source, rating);
      if (!label) return;
      const badge = document.createElement("span");
      badge.className = "public-rating-badge";
      badge.textContent = label;
      line.append(badge);
    });
    line.hidden = !line.childElementCount;
  });
}

async function loadCardRatings(container, movies) {
  const ids = [...new Set(movies.map((movie) => Number(movie.movie_id)).filter(Number.isSafeInteger))];
  const missing = ids.filter((id) => !externalRatings.has(id));
  if (missing.length) {
    try {
      const params = new URLSearchParams();
      missing.forEach((id) => params.append("movie_ids", String(id)));
      const values = await request("/movies/external-ratings?" + params.toString());
      values.forEach((value) => externalRatings.set(Number(value.movie_id), value));
    } catch {
      return;
    }
  }
  ids.forEach((id) => {
    const value = externalRatings.get(id);
    if (value) renderCardRating(container, id, value);
  });
}

function renderDialogRatings(data) {
  const grid = $("#dialog-ratings");
  const state = $("#dialog-ratings-state");
  grid.replaceChildren();
  [["IMDb", data.imdb], ["TMDB", data.tmdb]].forEach(([source, rating]) => {
    const hasScore = rating && rating.rating !== null && rating.rating !== undefined
      && Number.isFinite(Number(rating.rating));
    if (!rating || (!hasScore && !rating.url)) return;
    const card = document.createElement("article");
    card.className = "external-rating-card";
    const brand = document.createElement("span");
    brand.className = "external-rating-source";
    brand.textContent = source + " community rating";
    const score = document.createElement("strong");
    score.className = "external-rating-score";
    score.textContent = hasScore
      ? "★ " + Number(rating.rating).toFixed(1) + " / 10"
      : "No rating available";
    const votes = document.createElement("span");
    votes.className = "external-rating-votes";
    votes.textContent = formatVotes(rating.vote_count) || "Vote count unavailable";
    card.append(brand, score, votes);
    if (rating.url) {
      const link = document.createElement("a");
      link.href = rating.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "View on " + source + " ↗";
      card.append(link);
    }
    grid.append(card);
  });
  state.textContent = grid.childElementCount ? "Ratings from the IMDb and TMDB communities." : "No external ratings are available for this title.";
}

function setConnection(status, message) {
  const connection = $("#connection");
  connection.className = "connection " + status;
  $(".connection > span:last-child", connection).textContent = message;
}

async function checkHealth() {
  try {
    const health = await request("/health");
    setConnection("online", "Connected · " + Number(health.movies_loaded).toLocaleString() + " films");
    $("#catalog-count").textContent = Number(health.movies_loaded).toLocaleString() + " stories in the collection";
  } catch {
    setConnection("offline", "Cinema unavailable");
  }
}

async function loadHomePicks() {
  const container = $("#home-picks");
  try {
    const movies = await request("/recommendations/users/" + profileId + "?limit=12");
    renderMovies(container, movies, "Let’s find your first favorite.", "Rate a film you love to shape recommendations for this profile.");
  } catch (error) {
    showEmpty(container, "Your picks couldn’t load.", error.message, true);
  }
}

async function loadRecommendations() {
  const container = $("#personal-results");
  container.innerHTML = '<div class="skeleton-grid"><span></span><span></span><span></span><span></span><span></span></div>';
  $("#profile-label").textContent = String(profileId);
  try {
    const movies = await request("/recommendations/users/" + profileId + "?limit=30");
    renderMovies(container, movies, "Your next story is one rating away.", "Explore the collection and rate a film you already love.");
  } catch (error) {
    showEmpty(container, "Recommendations aren’t available right now.", error.message, true);
  }
}

function makeSuggestion(movie) {
  const button = document.createElement("button");
  button.className = "suggestion";
  button.type = "button";
  const title = document.createElement("span");
  title.textContent = movie.title;
  const genre = document.createElement("small");
  genre.textContent = getGenres(movie).slice(0, 2).join(" · ");
  button.append(title, genre);
  button.addEventListener("click", () => {
    $("#movie-search").value = movie.title;
    $("#search-suggestions").hidden = true;
    showExplore([movie], movie.title);
  });
  return button;
}

function showExplore(movies, query) {
  currentSearchResults = movies;
  activeGenre = "";
  $("#search-caption").textContent = movies.length + (movies.length === 1 ? " film" : " films") + " matching “" + query + "”";
  const filterContainer = $("#genre-filters");
  filterContainer.replaceChildren();
  const genres = Array.from(new Set(movies.flatMap(getGenres))).sort((a, b) => a.localeCompare(b));
  if (genres.length > 1) {
    const all = makeFilterChip("All genres", "");
    all.classList.add("active");
    filterContainer.append(all);
    genres.forEach((genre) => filterContainer.append(makeFilterChip(genre, genre)));
  }
  renderFilteredResults();
}

function makeFilterChip(label, value) {
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "filter-chip";
  chip.textContent = label;
  chip.addEventListener("click", () => {
    activeGenre = value;
    $$(".filter-chip", $("#genre-filters")).forEach((item) => item.classList.toggle("active", item === chip));
    renderFilteredResults();
  });
  return chip;
}

function renderFilteredResults() {
  const filtered = activeGenre
    ? currentSearchResults.filter((movie) => getGenres(movie).includes(activeGenre))
    : currentSearchResults;
  renderMovies($("#explore-results"), filtered, "No films in this filter.", "Try another genre or search for a different title.");
}

async function searchMovies(query, limit = 30) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return request("/movies/search?" + params.toString());
}

async function runSearch(showSuggestions = true) {
  const query = $("#movie-search").value.trim();
  const suggestions = $("#search-suggestions");
  if (query.length < 2) {
    suggestions.hidden = true;
    if (!query) showEmpty($("#explore-results"), "Every great watch starts somewhere.", "Search a title to discover films from the catalog.");
    return;
  }
  $("#search-caption").textContent = "Searching the collection…";
  try {
    const movies = await searchMovies(query);
    if (showSuggestions) {
      suggestions.replaceChildren();
      movies.slice(0, 7).forEach((movie) => suggestions.append(makeSuggestion(movie)));
      suggestions.hidden = movies.length === 0;
    } else {
      suggestions.hidden = true;
      showExplore(movies, query);
    }
  } catch (error) {
    suggestions.hidden = true;
    showEmpty($("#explore-results"), "Search is unavailable.", error.message, true);
    $("#search-caption").textContent = "Could not search right now";
  }
}

async function openMovie(movie) {
  activeMovie = movie;
  const dialog = $("#movie-dialog");
  $("#dialog-title").textContent = movie.title;
  $("#dialog-year").textContent = getYear(movie.title) ? "Released " + getYear(movie.title) : "MovieLens catalog record";
  const genres = $("#dialog-genres");
  genres.replaceChildren();
  getGenres(movie).forEach((name) => {
    const tag = document.createElement("span");
    tag.className = "genre-tag";
    tag.textContent = name;
    genres.append(tag);
  });
  $("#dialog-poster").style.setProperty("--poster-color", PALETTE[hashTitle(movie.title) % PALETTE.length]);
  $("#dialog-similar-results").replaceChildren();
  $("#dialog-similar-results").innerHTML = '<div class="loading-state">Finding films with a similar feel…</div>';
  updateDialogWatchlistButton();
  $("#dialog-ratings").replaceChildren();
  $("#dialog-ratings-state").textContent = "Checking IMDb and TMDB…";
  dialog.showModal();
  try {
    let ratings = externalRatings.get(Number(movie.movie_id));
    if (!ratings) {
      const params = new URLSearchParams({ movie_ids: String(Number(movie.movie_id)) });
      [ratings] = await request("/movies/external-ratings?" + params.toString());
      if (ratings) externalRatings.set(Number(movie.movie_id), ratings);
    }
    if (ratings && activeMovie === movie) renderDialogRatings(ratings);
    else if (activeMovie === movie) $("#dialog-ratings-state").textContent = "No external ratings are available for this title.";
  } catch {
    if (activeMovie === movie) $("#dialog-ratings-state").textContent = "Community ratings are unavailable right now.";
  }
  try {
    const related = await request("/recommendations/similar/" + Number(movie.movie_id) + "?limit=5");
    renderMovies($("#dialog-similar-results"), related, "No similar titles found.", "Try another film from the collection.");
  } catch (error) {
    showEmpty($("#dialog-similar-results"), "Similar films aren’t available.", error.message, true);
  }
}

function updateDialogWatchlistButton() {
  if (!activeMovie) return;
  const saved = isSaved(activeMovie.movie_id);
  $("#dialog-watchlist").textContent = saved ? "✓ Saved to watchlist" : "＋ Add to watchlist";
}

function renderWatchlist() {
  const list = getWatchlist();
  const filter = $("#watchlist-filter").value;
  const sort = $("#watchlist-sort").value;
  const filtered = list.filter((movie) => !filter || getGenres(movie).includes(filter));
  if (sort === "title") filtered.sort((a, b) => a.title.localeCompare(b.title));
  else if (sort === "year") filtered.sort((a, b) => (Number(getYear(b.title)) || 0) - (Number(getYear(a.title)) || 0));
  else filtered.sort((a, b) => Number(b.saved_at || 0) - Number(a.saved_at || 0));
  $("#watchlist-summary").textContent = list.length + (list.length === 1 ? " saved film" : " saved films");
  const filters = Array.from(new Set(list.flatMap(getGenres))).sort((a, b) => a.localeCompare(b));
  const select = $("#watchlist-filter");
  const selected = select.value;
  select.replaceChildren();
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "All genres";
  select.append(all);
  filters.forEach((genre) => {
    const option = document.createElement("option");
    option.value = genre;
    option.textContent = genre;
    select.append(option);
  });
  select.value = filters.includes(selected) ? selected : "";
  const container = $("#watchlist-results");
  if (!filtered.length) {
    const message = list.length
      ? "No saved films match this genre."
      : "Save a film from Explore or your recommendations and it will be waiting here.";
    showEmpty(container, list.length ? "A quieter shelf." : "Your watchlist is ready.", message);
    return;
  }
  renderMovies(container, filtered, "Your watchlist is empty.", "Save a film to keep it close.");
}

function showPage(page) {
  $$(".page").forEach((section) => section.classList.toggle("active", section.id === "page-" + page));
  $$(".nav-link").forEach((link) => link.classList.toggle("active", link.dataset.pageLink === page));
  $("#primary-nav").classList.remove("open");
  $("#mobile-menu").setAttribute("aria-expanded", "false");
  $("#mobile-backdrop").classList.remove("open");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (page === "home") loadHomePicks();
  if (page === "recommendations") loadRecommendations();
  if (page === "watchlist") renderWatchlist();
  if (page === "explore") setTimeout(() => $("#movie-search").focus({ preventScroll: true }), 80);
}

function openProfileDialog() {
  $("#profile-id-input").value = String(profileId);
  $("#profile-dialog").showModal();
}

$$("[data-page-link]").forEach((control) => {
  control.addEventListener("click", (event) => {
    event.preventDefault();
    showPage(control.dataset.pageLink);
  });
});

$("#movie-search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => runSearch(true), 220);
});
$("#movie-search").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    runSearch(false);
  } else if (event.key === "Escape") {
    $("#search-suggestions").hidden = true;
  }
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".search-panel")) $("#search-suggestions").hidden = true;
});
$("#refresh-picks").addEventListener("click", loadRecommendations);
$("#watchlist-filter").addEventListener("change", renderWatchlist);
$("#watchlist-sort").addEventListener("change", renderWatchlist);
$("#profile-button").addEventListener("click", openProfileDialog);
$("#profile-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const nextId = Number($("#profile-id-input").value);
  if (!Number.isSafeInteger(nextId) || nextId <= 0) {
    showToast("Enter a positive whole-number profile ID.", true);
    return;
  }
  profileId = nextId;
  localStorage.setItem(PROFILE_KEY, String(profileId));
  $("#profile-dialog").close();
  if ($("#page-home").classList.contains("active")) loadHomePicks();
  if ($("#page-recommendations").classList.contains("active")) loadRecommendations();
  showToast("Profile updated.");
});
$("[data-close-profile]").addEventListener("click", () => $("#profile-dialog").close());
$("#movie-dialog .dialog-close").addEventListener("click", () => $("#movie-dialog").close());
$("#dialog-watchlist").addEventListener("click", () => {
  if (activeMovie) toggleWatchlist(activeMovie);
  updateDialogWatchlistButton();
});
$("#dialog-similar").addEventListener("click", () => {
  $("#movie-dialog").close();
  showPage("explore");
  $("#movie-search").value = activeMovie ? activeMovie.title : "";
  runSearch(false);
});
$("#mobile-menu").addEventListener("click", () => {
  const isOpen = $("#mobile-menu").getAttribute("aria-expanded") === "true";
  $("#mobile-menu").setAttribute("aria-expanded", String(!isOpen));
  $("#primary-nav").classList.toggle("open", !isOpen);
  $("#mobile-backdrop").classList.toggle("open", !isOpen);
});
$("#mobile-backdrop").addEventListener("click", () => {
  $("#primary-nav").classList.remove("open");
  $("#mobile-menu").setAttribute("aria-expanded", "false");
  $("#mobile-backdrop").classList.remove("open");
});
$("#movie-dialog").addEventListener("click", (event) => {
  if (event.target === $("#movie-dialog")) $("#movie-dialog").close();
});

const nav = $(".primary-nav");
nav.id = "primary-nav";
$("#profile-label").textContent = String(profileId);
updateWatchlistCount();
checkHealth();
loadHomePicks();
