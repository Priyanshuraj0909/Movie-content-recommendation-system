const API = "/api";
const $ = (selector) => document.querySelector(selector);
const profileInput = $("#profile-id");
let selectedSeed = null;
let seedDebounce;
let toastTimeout;

function profileId() {
  const value = Math.max(1, Number.parseInt(profileInput.value, 10) || 1001);
  profileInput.value = String(value);
  localStorage.setItem("cinematch.profileId", String(value));
  $("#profile-label").textContent = String(value);
  return value;
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try { detail = (await response.json()).detail || detail; } catch { /* Keep the status message. */ }
    throw new Error(detail);
  }
  return response.json();
}

function setConnection(state, message) {
  const indicator = $("#connection");
  indicator.className = `connection ${state}`;
  indicator.lastElementChild.textContent = message;
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => element.classList.remove("show"), 3000);
}

function showError(container, message) {
  container.replaceChildren();
  const state = document.createElement("div");
  state.className = "empty-state";
  const text = document.createElement("p");
  text.textContent = message;
  state.append(text);
  container.append(state);
}

function makeMovieCard(movie, key) {
  const card = document.createElement("article");
  card.className = "movie-card";
  const title = document.createElement("h3");
  title.className = "movie-title";
  title.textContent = movie.title;
  const meta = document.createElement("div");
  meta.className = "movie-meta";
  meta.textContent = movie.genres || "Genre not listed";
  card.append(title, meta);
  if (Number.isFinite(movie.score)) {
    const score = document.createElement("span");
    score.className = "movie-score";
    score.textContent = `Match ${Math.round(movie.score * 100)}%`;
    card.append(score);
  }
  if (Number.isFinite(movie.predicted_rating)) {
    const predicted = document.createElement("div");
    predicted.className = "movie-meta";
    predicted.style.marginTop = "6px";
    predicted.textContent = `Predicted rating ${movie.predicted_rating.toFixed(1)} / 5`;
    card.append(predicted);
  }
  const actions = document.createElement("div");
  actions.className = "card-actions";
  const select = document.createElement("select");
  select.setAttribute("aria-label", `Your rating for ${movie.title}`);
  for (let value = 5; value >= 0.5; value -= 0.5) {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = `${value.toFixed(1)} ★`;
    select.append(option);
  }
  const save = document.createElement("button");
  save.type = "button";
  save.className = "rate-button";
  save.textContent = "Save rating";
  save.addEventListener("click", async () => {
    save.disabled = true;
    save.textContent = "Saving…";
    try {
      await request("/ratings", {
        method: "POST",
        body: JSON.stringify({ user_id: profileId(), movie_id: movie.movie_id, rating: Number(select.value) }),
      });
      toast("Rating saved. Your picks will keep learning from it.");
    } catch (error) {
      toast(error.message);
    } finally {
      save.disabled = false;
      save.textContent = "Save rating";
    }
  });
  actions.append(select, save);
  card.append(actions);
  return card;
}

function renderMovies(container, movies) {
  container.replaceChildren();
  if (!movies.length) {
    showError(container, "No films found. Try another title or rate a few favorites first.");
    return;
  }
  const grid = document.createElement("div");
  grid.className = "movie-grid";
  movies.forEach((movie, index) => grid.append(makeMovieCard(movie, index)));
  container.append(grid);
}

async function checkHealth() {
  try {
    const health = await request("/health");
    setConnection("online", `Connected · ${health.movies_loaded.toLocaleString()} movies`);
  } catch {
    setConnection("offline", "Recommendation service unavailable");
  }
}

async function searchMovies(query, limit = 20) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return request(`/movies/search?${params}`);
}

async function discover() {
  const query = $("#movie-search").value.trim();
  const results = $("#discover-results");
  if (!query) {
    showError(results, "Search for a film, then rate it to shape your personal picks.");
    return;
  }
  results.innerHTML = '<div class="loading-state">Searching the collection…</div>';
  try { renderMovies(results, await searchMovies(query)); }
  catch (error) { showError(results, error.message); }
}

async function loadPicks() {
  const container = $("#personal-results");
  container.innerHTML = '<div class="loading-state">Finding a few good stories…</div>';
  try { renderMovies(container, await request(`/recommendations/users/${profileId()}?limit=12`)); }
  catch (error) { showError(container, error.message); }
}

async function searchSeeds() {
  const query = $("#similar-search").value.trim();
  const list = $("#similar-seeds");
  const results = $("#similar-results");
  selectedSeed = null;
  results.replaceChildren();
  if (query.length < 2) { list.replaceChildren(); return; }
  try {
    const movies = await searchMovies(query, 8);
    list.replaceChildren();
    movies.forEach((movie) => {
      const option = document.createElement("button");
      option.type = "button";
      option.className = "seed-option";
      const name = document.createElement("span");
      name.textContent = movie.title;
      const genre = document.createElement("small");
      genre.textContent = movie.genres || "Genre not listed";
      option.append(name, genre);
      option.addEventListener("click", async () => {
        selectedSeed = movie;
        list.querySelectorAll(".seed-option").forEach((item) => item.classList.remove("selected"));
        option.classList.add("selected");
        results.innerHTML = '<div class="loading-state">Finding films with a similar feel…</div>';
        try { renderMovies(results, await request(`/recommendations/similar/${movie.movie_id}?limit=8`)); }
        catch (error) { showError(results, error.message); }
      });
      list.append(option);
    });
    if (!movies.length) showError(list, "No matching titles yet.");
  } catch (error) { showError(list, error.message); }
}

function activatePage(page) {
  document.querySelectorAll(".nav-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.page === page));
  document.querySelectorAll(".page").forEach((section) => section.classList.toggle("active", section.id === `page-${page}`));
  if (page === "for-you") loadPicks();
}

function createAnonymousProfileId() {
  const words = new Uint32Array(2);
  crypto.getRandomValues(words);
  const safeIntegerLimit = 9_007_199_254_740_991n;
  const generated = ((BigInt(words[0]) << 32n) | BigInt(words[1])) % safeIntegerLimit;
  return String(generated || 1n);
}

profileInput.value = localStorage.getItem("cinematch.profileId") || createAnonymousProfileId();
profileId();
profileInput.addEventListener("change", () => {
  profileId();
  if ($("#page-for-you").classList.contains("active")) loadPicks();
});
$("#profile-minus").addEventListener("click", () => { profileInput.value = String(Math.max(1, profileId() - 1)); profileInput.dispatchEvent(new Event("change")); });
$("#profile-plus").addEventListener("click", () => { profileInput.value = String(profileId() + 1); profileInput.dispatchEvent(new Event("change")); });
document.querySelectorAll(".nav-tab").forEach((tab) => tab.addEventListener("click", () => activatePage(tab.dataset.page)));
$("#movie-search").addEventListener("input", () => { clearTimeout(seedDebounce); seedDebounce = setTimeout(discover, 250); });
$("#movie-search").addEventListener("keydown", (event) => { if (event.key === "Enter") discover(); });
$("#similar-search").addEventListener("input", () => { clearTimeout(seedDebounce); seedDebounce = setTimeout(searchSeeds, 250); });
$("#refresh-picks").addEventListener("click", loadPicks);
checkHealth();
