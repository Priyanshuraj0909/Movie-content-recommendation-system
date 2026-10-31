const API = "/api";
const REQUEST_TIMEOUT_MS = 15000;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const PALETTE = ["#6c51aa", "#8b4c75", "#375f77", "#83603e", "#514b8b", "#397061", "#8c4850", "#526483"];
const WATCHLIST_KEY = "cinematch.watchlist";
const SESSION_KEY = "cinematch.privateProfile";
let privateProfile = null;
try { privateProfile = JSON.parse(localStorage.getItem(SESSION_KEY) || "null"); } catch { /* Create a profile below. */ }
let profileId = privateProfile?.user_id || null;
let profileGeneration = 0;
let currentSearchResults = [];
let activeGenre = "";
let searchTimer;
let searchSequence = 0;
let toastTimer;
let activeMovie = null;
let ratingCount = 0;
let ratedMovies = new Map();
let movieStates = new Map();
let pickMode = "balanced";
let libraryOffset = 0;
let librarySequence = 0;
let onboardingSequence = 0;
let homeSequence = 0;
let picksSequence = 0;
const externalRatings = new Map();

function readStoredList(key) {
  try { const value = JSON.parse(localStorage.getItem(key) || "[]"); return Array.isArray(value) ? value : []; }
  catch { return []; }
}

async function initializeProfile() {
  const generation = profileGeneration;
  if (!privateProfile?.token || !Number.isSafeInteger(privateProfile.user_id)) {
    const created = await request("/profiles", { method: "POST" });
    if (generation !== profileGeneration) return;
    privateProfile = created;
    profileId = created.user_id;
    localStorage.setItem(SESSION_KEY, JSON.stringify(created));
  }
  const currentId = profileId;
  const headers = { "X-Profile-Token": privateProfile.token };
  const [history, preferences, remote] = await Promise.all([
    request("/profiles/" + currentId + "/ratings", { headers }),
    request("/profiles/" + currentId + "/preferences", { headers }),
    request("/profiles/" + currentId + "/watchlist", { headers }),
  ]);
  if (generation !== profileGeneration) return;
  ratedMovies = new Map(history.map((row) => [Number(row.movie_id), Number(row.rating)]));
  movieStates = new Map(preferences.map((row) => [Number(row.movie_id), row.state]));
  ratingCount = history.length;
  updateOnboarding();
  const ownerKey = "cinematch.watchlistImportOwner";
  const doneKey = "cinematch.watchlistImportSaved";
  const outboxKey = WATCHLIST_KEY + ".pending." + currentId;
  if (!localStorage.getItem(ownerKey)) localStorage.setItem(ownerKey, String(currentId));
  let pending = readStoredList(outboxKey);
  if (!localStorage.getItem(doneKey) && localStorage.getItem(ownerKey) === String(currentId)) {
    pending = [...pending, ...readStoredList(WATCHLIST_KEY)];
  }
  pending = pending.filter((movie, i, entries) => Number.isSafeInteger(movie.movie_id) && entries.findIndex((entry) => entry.movie_id === movie.movie_id) === i);
  const remaining = [];
  const importStarted = performance.now();
  for (let i = 0; i < pending.length; i += 1) {
    if (generation !== profileGeneration) return;
    const movie = pending[i];
    if (remote.some((entry) => entry.movie_id === movie.movie_id)) continue;
    // Preserve the outbox and continue next time instead of delaying opening
    // the app for a large legacy list. Each in-flight write is also time bounded.
    if (i >= 500 || performance.now() - importStarted >= 1000) { remaining.push(...pending.slice(i)); break; }
    try {
      await request("/profiles/" + currentId + "/watchlist", { headers,
        method: "PUT", body: JSON.stringify({ movie_id: movie.movie_id }),
      });
      remote.push(movie);
    } catch { remaining.push(...pending.slice(i)); break; }
  }
  if (generation !== profileGeneration) return;
  // Remote storage is authoritative; only a preserved migration outbox is replayed.
  localStorage.setItem(outboxKey, JSON.stringify(remaining));
  if (localStorage.getItem(ownerKey) === String(currentId)) localStorage.setItem(doneKey, "1");
  remaining.forEach((movie) => { if (!remote.some((entry) => entry.movie_id === movie.movie_id)) remote.push(movie); });
  saveWatchlist(remote);
  $("#profile-label").textContent = "Private";
}

function updateOnboarding() {
  $("#taste-progress").textContent = ratingCount >= 5
    ? "Your taste profile is taking shape. Keep rating to refine your picks."
    : "Start with 5 films you know · " + ratingCount + " rated";
  $("#onboarding-progress").value = Math.min(ratingCount, 5);
  $("#onboarding-progress-label").textContent = Math.min(ratingCount, 5) + " of 5 films rated";
  $("#onboarding-hint").textContent = ratingCount >= 5 ? "Your first five are saved. Explore your picks whenever you’re ready." : "Every rating helps describe your taste. Fewer than five is fine too.";
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(API + path, {
      ...options,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(privateProfile?.token ? { "X-Profile-Token": privateProfile.token } : {}), ...(options.headers || {}) },
    });
    if (response.redirected || !response.headers.get("content-type")?.includes("application/json")) {
      throw new Error("The cinema service is unavailable or requires deployment sign-in. Please try again shortly.");
    }
    if (!response.ok) {
      let message = "The cinema service returned " + response.status + ".";
      const payload = await response.json();
      if (typeof payload.detail === "string") message = payload.detail;
      throw new Error(message);
    }
    return await response.json();
  } catch (error) {
    if (controller.signal.aborted) throw new Error("The cinema is taking too long to respond. Please try again.");
    if (error instanceof TypeError) throw new Error("Couldn’t reach the cinema. Check your connection and try again.");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function getWatchlist() {
  try {
    const value = JSON.parse(localStorage.getItem(WATCHLIST_KEY + "." + profileId) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function saveWatchlist(items) {
  localStorage.setItem(WATCHLIST_KEY + "." + profileId, JSON.stringify(items));
  const outbox = WATCHLIST_KEY + ".pending." + profileId;
  localStorage.setItem(outbox, JSON.stringify(readStoredList(outbox).filter((movie) => items.some((entry) => entry.movie_id === movie.movie_id))));
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

function showEmpty(container, title, message, isError = false, retry = null) {
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
  if (retry) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button-outline connection-retry";
    button.textContent = "Try again";
    button.addEventListener("click", retry);
    panel.append(button);
  }
  container.append(panel);
}

function isSaved(movieId) {
  return getWatchlist().some((movie) => Number(movie.movie_id) === Number(movieId));
}

async function toggleWatchlist(movie) {
  try {
  await profileReady;
  const list = getWatchlist();
  const existing = list.findIndex((item) => Number(item.movie_id) === Number(movie.movie_id));
  if (existing >= 0) {
    await request("/profiles/" + profileId + "/watchlist/" + movie.movie_id, { method: "DELETE" });
    list.splice(existing, 1);
    saveWatchlist(list);
    showToast("Removed from your watchlist.");
  } else {
    await request("/profiles/" + profileId + "/watchlist", {
      method: "PUT", body: JSON.stringify({ movie_id: movie.movie_id }),
    });
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
  } catch (error) { showToast(error.message, true); }
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
  const existingRating = movie.rating ?? ratedMovies.get(Number(movie.movie_id));
  if (Number.isFinite(existingRating)) select.value = String(existingRating);
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
      await profileReady;
      await request("/ratings", {
        method: "POST",
        body: JSON.stringify({ user_id: profileId, movie_id: Number(movie.movie_id), rating }),
      });
      ratedMovies.set(Number(movie.movie_id), rating);
      ratingCount = ratedMovies.size;
      updateOnboarding();
      showToast("Rating saved. Your picks now use this feedback.");
      refreshTasteViews();
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
  save.addEventListener("click", async (event) => {
    event.stopPropagation();
    await toggleWatchlist(movie);
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
    score.textContent = "Relevance " + Number(movie.score).toFixed(2);
    bottom.append(score);
  }
  const detail = document.createElement("button");
  detail.className = "movie-detail-link";
  detail.type = "button";
  detail.textContent = "Details";
  detail.addEventListener("click", () => openMovie(movie));
  bottom.append(detail);
  const explanation = document.createElement("p");
  explanation.className = "recommendation-reason";
  explanation.textContent = movie.reason || "";
  explanation.hidden = !movie.reason;
  info.append(title, genres, ratingLine, explanation, bottom, makeRatingControls(movie), makeStateControls(movie));
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
  for (let offset = 0; offset < missing.length; offset += 30) {
    try {
      const params = new URLSearchParams();
      missing.slice(offset, offset + 30).forEach((id) => params.append("movie_ids", String(id)));
      const values = await request("/movies/external-ratings?" + params.toString());
      values.forEach((value) => externalRatings.set(Number(value.movie_id), value));
    } catch { /* Keep movie discovery usable when a provider is unavailable. */ }
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
  const health = await request("/health");
  if (health.status !== "ok" || !Number.isSafeInteger(health.movies_loaded)) {
    throw new Error("The cinema returned an unexpected response. Please try again.");
  }
  $("#catalog-count").textContent = Number(health.movies_loaded).toLocaleString() + " stories in the collection";
  return health;
}

async function loadHomePicks() {
  const sequence = ++homeSequence;
  const generation = profileGeneration;
  const container = $("#home-picks");
  try {
    await profileReady;
    const movies = await request("/recommendations/users/" + profileId + "?limit=12");
    if (sequence !== homeSequence || generation !== profileGeneration) return;
    renderMovies(container, movies, "Let’s find your first favorite.", "Rate a film you love to shape recommendations for this profile.");
  } catch (error) {
    if (sequence !== homeSequence || generation !== profileGeneration) return;
    showEmpty(container, "Your picks couldn’t load.", error.message, true, retryConnection);
  }
}

async function loadRecommendations() {
  const sequence = ++picksSequence;
  const generation = profileGeneration;
  const container = $("#personal-results");
  container.innerHTML = '<div class="skeleton-grid"><span></span><span></span><span></span><span></span><span></span></div>';
  $("#profile-label").textContent = "Private";
  try {
    await profileReady;
    const movies = await request("/recommendations/users/" + profileId + "?limit=30&mode=" + pickMode);
    if (sequence !== picksSequence || generation !== profileGeneration) return;
    renderMovies(container, movies, "Your next story is one rating away.", "Explore the collection and rate a film you already love.");
  } catch (error) {
    if (sequence !== picksSequence || generation !== profileGeneration) return;
    showEmpty(container, "Recommendations aren’t available right now.", error.message, true, retryConnection);
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
  const story = $("#discovery-mode").value === "story";
  if (story) {
    if ($("#max-runtime").value) params.set("max_runtime", $("#max-runtime").value);
    if ($("#story-language").value.trim()) params.set("language", $("#story-language").value.trim());
  }
  return request((story ? "/movies/semantic-search?" : "/movies/search?") + params.toString());
}

async function runSearch(showSuggestions = true) {
  const sequence = ++searchSequence;
  const query = $("#movie-search").value.trim();
  const suggestions = $("#search-suggestions");
  const story = $("#discovery-mode").value === "story";
  if (query.length < (story ? 3 : 2)) {
    suggestions.hidden = true;
    if (!query) showEmpty($("#explore-results"), "Every great watch starts somewhere.", "Search a title to discover films from the catalog.");
    return;
  }
  $("#search-caption").textContent = "Searching the collection…";
  try {
    const movies = await searchMovies(query);
    if (sequence !== searchSequence) return;
    if (showSuggestions && !story) {
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
  $("#plot-section").hidden = true;
  $("#plot-section").open = false;
  $("#movie-metadata").textContent = "Loading movie information…";
  loadMovieDetails(movie);
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
  if (page === "library") loadLibrary();
  if (page === "explore") setTimeout(() => $("#movie-search").focus({ preventScroll: true }), 80);
}

async function openProfileDialog() {
  $("#profile-dialog").showModal();
  try {
    await profileReady;
    $("#recovery-code").value = profileId + "." + privateProfile.token;
    const ratings = await request("/profiles/" + profileId + "/ratings");
    $("#rating-history").textContent = ratings.length + " rated films saved to this profile.";
  } catch (error) { $("#rating-history").textContent = error.message; }
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
    clearTimeout(searchTimer);
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
$("#profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = $("#profile-id-input").value.trim();
  const match = value.match(/^(\d+)\.([A-Za-z0-9_-]{40,64})$/);
  if (!match || !Number.isSafeInteger(Number(match[1]))) {
    showToast("Enter the complete private recovery code.", true);
    return;
  }
  const candidate = { user_id: Number(match[1]), token: match[2] };
  const headers = { "X-Profile-Token": candidate.token };
  try {
    // Validate every remote read before changing the active identity or cache.
    const [ratings, list, preferences] = await Promise.all([
      request("/profiles/" + candidate.user_id + "/ratings", { headers }),
      request("/profiles/" + candidate.user_id + "/watchlist", { headers }),
      request("/profiles/" + candidate.user_id + "/preferences", { headers }),
    ]);
    localStorage.setItem(SESSION_KEY, JSON.stringify(candidate));
    profileGeneration += 1;
    privateProfile = candidate;
    profileId = candidate.user_id;
    ratedMovies = new Map(ratings.map((row) => [Number(row.movie_id), Number(row.rating)]));
    movieStates = new Map(preferences.map((row) => [Number(row.movie_id), row.state]));
    ratingCount = ratings.length;
    updateOnboarding();
    saveWatchlist(list);
    profileReady = Promise.resolve();
    $("#profile-dialog").close();
    refreshTasteViews();
    showToast("Private profile restored.");
  } catch (error) {
    showToast(error.message, true);
  }
});
$("[data-close-profile]").addEventListener("click", () => $("#profile-dialog").close());
$("#movie-dialog .dialog-close").addEventListener("click", () => $("#movie-dialog").close());
$("#dialog-watchlist").addEventListener("click", async () => {
  if (activeMovie) await toggleWatchlist(activeMovie);
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
$("#profile-label").textContent = "Private";
let profileReady;
let connectionAttempt = null;
function retryConnection() {
  if (connectionAttempt) return connectionAttempt;
  const generation = profileGeneration;
  setConnection("", "Connecting…");
  $("#home-picks").innerHTML = '<div class="loading-state">Getting your films ready…</div>';
  profileReady = initializeProfile();
  // Observe both failures immediately; a healthy API must not hide a profile error.
  connectionAttempt = Promise.allSettled([checkHealth(), profileReady]).then(([health, profile]) => {
    if (generation !== profileGeneration) return;
    if (health.status === "fulfilled" && profile.status === "fulfilled") {
      setConnection("online", "Connected · " + health.value.movies_loaded.toLocaleString() + " films");
    } else {
      setConnection("offline", "Connection interrupted");
      if (profile.status === "rejected") {
        showEmpty($("#home-picks"), "Your picks couldn’t load.", profile.reason.message, true, retryConnection);
      }
    }
  }).finally(() => { connectionAttempt = null; });
  loadHomePicks();
  if ($("#page-recommendations").classList.contains("active")) loadRecommendations();
  checkCapabilities();
  return connectionAttempt;
}
updateWatchlistCount();
retryConnection();

$("#show-recovery").addEventListener("click", () => {
  const input = $("#recovery-code");
  input.type = input.type === "password" ? "text" : "password";
});
$("#profile-dialog").addEventListener("close", () => { $("#recovery-code").type = "password"; });

async function loadMovieDetails(movie) {
  try {
    const details = await request("/movies/" + movie.movie_id);
    if (activeMovie?.movie_id !== movie.movie_id) return;
    const metadata = [];
    if (details.runtime_minutes) metadata.push(Math.round(details.runtime_minutes) + " minutes");
    if (details.languages?.length) metadata.push(details.languages.join(" · "));
    $("#movie-metadata").textContent = metadata.join(" · ") || "Runtime and language information are unavailable.";
    $("#plot-section").hidden = !details.summary;
    $("#movie-plot").textContent = details.summary || "";
    if (details.source_url) $("#plot-source").href = details.source_url;
    if (details.license_url) $("#plot-license").href = details.license_url;
    if (!details.summary) $("#movie-metadata").textContent += " No verified plot summary is available.";
  } catch {
    if (activeMovie?.movie_id === movie.movie_id) $("#movie-metadata").textContent = "Movie details are unavailable right now.";
  }
}

async function checkCapabilities() {
  try {
    const capabilities = await request("/capabilities");
    $("#discovery-mode option[value=story]").disabled = !capabilities.semantic_search;
    $("#discovery-status").textContent = capabilities.semantic_search
      ? "Describe a story or mood to search " + Number(capabilities.semantic_movies).toLocaleString() + " films with verified plot summaries."
      : "Title search is ready. Story search is not available on this deployment yet.";
  } catch { $("#discovery-status").textContent = "Title search is available when the catalog is connected."; }
}
$("#discovery-mode").addEventListener("change", () => {
  const story = $("#discovery-mode").value === "story";
  $("#max-runtime").disabled = !story;
  $("#story-language").disabled = !story;
  $("#movie-search").placeholder = story ? "A hopeful story about space exploration…" : "Search by movie title…";
  $("#movie-search").setAttribute("aria-label", story ? "Describe a story or mood" : "Search movies by title");
  runSearch(false);
});
$("#max-runtime").addEventListener("change", () => runSearch(false));
$("#story-language").addEventListener("change", () => runSearch(false));

const tmdbLogo = $(".tmdb-credit img");
if (tmdbLogo) {
  tmdbLogo.addEventListener("error", () => { tmdbLogo.hidden = true; });
  if (tmdbLogo.complete && !tmdbLogo.naturalWidth) tmdbLogo.hidden = true;
}

function refreshTasteViews() {
  if ($("#page-home").classList.contains("active")) loadHomePicks();
  if ($("#page-recommendations").classList.contains("active")) loadRecommendations();
  if ($("#page-library").classList.contains("active")) loadLibrary();
  if ($("#onboarding-dialog").open) loadOnboardingMovies();
}

function makeStateControls(movie) {
  const controls = document.createElement("div");
  controls.className = "movie-feedback";
  const state = movieStates.get(Number(movie.movie_id)) || movie.state || "none";
  const actions = state === "none"
    ? [["watched", "Watched", "Mark " + movie.title + " watched"], ["not_interested", "Not interested", "Not interested in " + movie.title]]
    : [["none", state === "watched" ? "Undo watched" : "Undo not interested", "Undo feedback for " + movie.title]];
  actions.forEach(([next, label, accessible]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.setAttribute("aria-label", accessible);
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await profileReady;
        await request("/profiles/" + profileId + "/preferences", {
          method: "PUT", body: JSON.stringify({ movie_id: Number(movie.movie_id), state: next }),
        });
        movieStates.set(Number(movie.movie_id), next);
        movie.state = next;
        controls.replaceWith(makeStateControls(movie));
        showToast(next === "none" ? "Feedback cleared. Your ratings are unchanged." : next === "watched" ? "Marked watched. It will stay out of your picks." : "Saved. This film will stay out of your picks.");
        refreshTasteViews();
      } catch (error) { showToast(error.message, true); }
      finally { button.disabled = false; }
    });
    controls.append(button);
  });
  return controls;
}

function makeTasteEntry(movie) {
  const entry = document.createElement("article");
  entry.className = "taste-entry";
  entry.dataset.movieId = String(movie.movie_id);
  const text = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = movie.title;
  const summary = document.createElement("p");
  const labels = [];
  if (Number.isFinite(movie.rating)) labels.push("Your rating: " + movie.rating.toFixed(1) + " ★");
  if (movie.state === "watched") labels.push("Marked watched");
  if (movie.state === "not_interested") labels.push("Not interested");
  summary.textContent = labels.join(" · ") || getGenres(movie).join(" · ");
  text.append(title, summary);
  const actions = document.createElement("div");
  actions.className = "taste-entry-actions";
  if (movie.available !== false) actions.append(makeRatingControls(movie));
  if (movie.available !== false || movie.state !== "none") actions.append(makeStateControls(movie));
  entry.append(text, actions);
  return entry;
}

async function loadLibrary(append = false) {
  const sequence = ++librarySequence;
  const container = $("#library-results");
  const more = $("#library-more");
  more.disabled = true;
  if (!append) {
    libraryOffset = 0;
    container.textContent = "Loading your taste profile…";
  }
  try {
    await profileReady;
    const params = new URLSearchParams({ view: $("#library-filter").value, limit: "20", offset: String(libraryOffset) });
    const data = await request("/profiles/" + profileId + "/library?" + params);
    if (sequence !== librarySequence) return;
    ratingCount = data.rated_count;
    updateOnboarding();
    $("#library-summary").textContent = data.rated_count + " rated · " + data.watched_count + " marked watched · " + data.dismissed_count + " not interested";
    if (!append) container.replaceChildren();
    data.items.forEach((movie) => container.append(makeTasteEntry(movie)));
    libraryOffset += data.items.length;
    more.hidden = libraryOffset >= data.total;
    if (!data.total) showEmpty(container, "Your taste starts here.", "Rate a familiar film or mark something watched. Your choices will be waiting here.");
  } catch (error) {
    if (sequence === librarySequence) showEmpty(container, "Your taste profile couldn’t load.", error.message, true);
  } finally { if (sequence === librarySequence) more.disabled = false; }
}

async function loadOnboardingMovies() {
  const sequence = ++onboardingSequence;
  const container = $("#onboarding-results");
  const query = $("#onboarding-search").value.trim();
  container.textContent = "Finding familiar stories…";
  try {
    await profileReady;
    const films = query
      ? await request("/movies/search?" + new URLSearchParams({ q: query, limit: "20" }))
      : await request("/recommendations/users/" + profileId + "?limit=12");
    if (sequence !== onboardingSequence) return;
    const available = films.filter((movie) => !ratedMovies.has(Number(movie.movie_id)) && (!movieStates.get(Number(movie.movie_id)) || movieStates.get(Number(movie.movie_id)) === "none"));
    container.replaceChildren();
    available.slice(0, 8).forEach((movie) => container.append(makeTasteEntry(movie)));
    if (!available.length) showEmpty(container, "Try another familiar title.", "Already rated films are saved in Your taste. Search for another film you know.");
  } catch (error) {
    if (sequence === onboardingSequence) showEmpty(container, "Films couldn’t load.", error.message, true);
  }
}

$$("[data-start-onboarding]").forEach((button) => button.addEventListener("click", () => {
  updateOnboarding();
  $("#onboarding-dialog").showModal();
  loadOnboardingMovies();
}));
$("#close-onboarding").addEventListener("click", () => $("#onboarding-dialog").close());
$("#finish-onboarding").addEventListener("click", () => {
  $("#onboarding-dialog").close();
  showPage("recommendations");
});
$("#onboarding-search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  loadOnboardingMovies();
});
$("#library-filter").addEventListener("change", () => loadLibrary());
$("#library-more").addEventListener("click", () => loadLibrary(true));
$$("[data-pick-mode]").forEach((button) => button.addEventListener("click", () => {
  pickMode = button.dataset.pickMode;
  $$("[data-pick-mode]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
  $("#pick-mode-caption").textContent = pickMode === "discovery"
    ? "A wider mix of story themes inspired by your taste."
    : "Community favorites shaped by your ratings.";
  loadRecommendations();
}));
