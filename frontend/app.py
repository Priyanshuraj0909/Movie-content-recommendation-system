"""CineMatch Streamlit interface for browsing and rating movies."""

from __future__ import annotations

from html import escape

import streamlit as st

try:
    from frontend.api_client import APIError, RecommendationAPI
except ModuleNotFoundError:
    # Streamlit adds the entrypoint's folder to sys.path when launching this file.
    from api_client import APIError, RecommendationAPI

st.set_page_config(
    page_title="CineMatch | Find your next favorite",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root { --ink:#f6f2ea; --muted:#aaa8ad; --gold:#e7b866; --wine:#a63f50; }
    .stApp { background: radial-gradient(ellipse at 76% 0%, #35232b 0,
      #17171d 40%, #111216 100%); color:var(--ink); }
    [data-testid="stSidebar"] { background:#15151a; border-right:1px solid #ffffff14; }
    h1,h2,h3 { color:var(--ink) !important; font-family:Georgia, serif !important; }
    p, label, [data-testid="stCaptionContainer"] { color:var(--muted); }
    .hero { padding:2.2rem 2.5rem; border:1px solid #ffffff18; border-radius:24px;
      background:linear-gradient(115deg,#3b2831dd,#1b1c24e8 63%,#252532dd);
      box-shadow:0 24px 70px #0005; margin:0 0 1.5rem; }
    .eyebrow { color:var(--gold); font-size:.78rem; letter-spacing:.19em;
      font-weight:700; text-transform:uppercase; }
    .hero-title { font:700 clamp(2.4rem,5vw,4rem)/1.05 Georgia,serif; margin:.65rem 0; }
    .hero-copy { color:#c2bec3; font-size:1.05rem; max-width:640px; margin:0; }
    .movie-card { min-height:138px; padding:1.15rem; margin:.2rem 0 .65rem; border-radius:17px;
      border:1px solid #ffffff16; background:linear-gradient(140deg,#25252d,#1b1b21); }
    .movie-title { color:var(--ink); font:600 1.12rem -apple-system,
      BlinkMacSystemFont,sans-serif; margin-bottom:.55rem; }
    .movie-meta { color:#aaa8ad; font-size:.84rem; }
    .score { color:var(--gold); font-size:.82rem; font-weight:600; margin-top:.75rem; }
    div.stButton > button { border-radius:12px; border:1px solid #ffffff24; min-height:2.65rem; }
    div.stButton > button[kind="primary"] {
      background:linear-gradient(100deg,#a63f50,#854154); border:0; }
    div[data-testid="stForm"] { border:0; padding:0; }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_api() -> RecommendationAPI:
    return RecommendationAPI(st.session_state.get("api_url", "http://127.0.0.1:8000"))


def show_movie_card(movie: dict, *, key: str, user_id: int, api: RecommendationAPI) -> None:
    movie_id = int(movie["movie_id"])
    score_html = (
        f'<div class="score">Match {float(movie["score"]):.0%}</div>'
        if movie.get("score") is not None
        else ""
    )
    predicted_html = (
        f'<div class="score">Predicted rating {float(movie["predicted_rating"]):.1f} / 5</div>'
        if movie.get("predicted_rating") is not None
        else ""
    )
    st.markdown(
        f"""<div class="movie-card">
          <div class="movie-title">{escape(str(movie['title']))}</div>
          <div class="movie-meta">{escape(str(movie.get('genres') or 'Genre not listed'))}</div>
          {score_html}
          {predicted_html}
        </div>""",
        unsafe_allow_html=True,
    )
    controls = st.columns([1, 1.3])
    with controls[0]:
        rating = st.selectbox(
            "Your rating",
            [5.0, 4.5, 4.0, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5],
            key=f"rating_{key}_{movie_id}",
            label_visibility="collapsed",
        )
    with controls[1]:
        if st.button("Save rating", key=f"save_{key}_{movie_id}", use_container_width=True):
            with st.spinner("Saving your rating…"):
                try:
                    api.save_rating(user_id, movie_id, rating)
                    st.session_state["last_saved"] = (user_id, movie["title"], rating)
                    st.success("Rating saved. Your recommendations can now learn from it.")
                except APIError as error:
                    st.error(str(error))


def show_cards(movies: list[dict], *, key: str, user_id: int, api: RecommendationAPI) -> None:
    if not movies:
        st.info("No movies found here yet. Try another search or rate a few films first.")
        return
    for start in range(0, len(movies), 2):
        columns = st.columns(2, gap="large")
        for column, movie in zip(columns, movies[start : start + 2], strict=False):
            with column:
                show_movie_card(movie, key=key, user_id=user_id, api=api)


api = get_api()
with st.sidebar:
    st.markdown("## 🎬 CineMatch")
    st.caption("A little more you in every recommendation.")
    st.text_input("Recommendation API", key="api_url", value="http://127.0.0.1:8000")
    user_id = int(
        st.number_input("Your local profile ID", min_value=1, value=1001, step=1)
    )
    page = st.radio(
        "Explore", ["Discover", "For you", "Similar films"], label_visibility="collapsed"
    )
    try:
        health = api.health()
        st.success(f"Connected · {health['movies_loaded']:,} movies")
    except APIError as error:
        st.warning("API offline")
        st.caption(str(error))
    st.markdown("---")
    st.caption("Ratings use local SQLite here and hosted PostgreSQL when configured.")

st.markdown(
    """<section class="hero"><div class="eyebrow">Your personal cinema guide</div>
    <div class="hero-title">Find your next<br>favorite story.</div>
    <p class="hero-copy">Search the collection, tell us what you love, and discover films
    that feel like they were picked just for you.</p></section>""",
    unsafe_allow_html=True,
)

if page == "Discover":
    st.subheader("Explore the collection")
    query = st.text_input(
        "Search by movie title", placeholder="Try a title like The Matrix…", key="movie_search"
    )
    if query.strip():
        with st.spinner("Searching the collection…"):
            try:
                results = api.search_movies(query.strip())
                st.caption(f"{len(results)} title(s) found")
                show_cards(results, key="search", user_id=user_id, api=api)
            except APIError as error:
                st.error(str(error))
    else:
        st.info("Search for a film, then rate it to shape your personal picks.")
elif page == "For you":
    st.subheader("Picked for your profile")
    st.caption("Rate films in Discover and your saved favorites will guide future picks.")
    last_saved = st.session_state.get("last_saved")
    if last_saved and last_saved[0] == user_id:
        st.caption(f"Your latest saved rating: {last_saved[1]} · {last_saved[2]:.1f} stars")
    with st.spinner("Finding a few good stories…"):
        try:
            results = api.recommendations(user_id)
            show_cards(results, key="personal", user_id=user_id, api=api)
        except APIError as error:
            st.error(str(error))

else:
    st.subheader("More like a favorite")
    movie_query = st.text_input("Find a movie to use as your starting point", key="similar_search")
    if movie_query.strip():
        try:
            seeds = api.search_movies(movie_query.strip(), limit=10)
            if seeds:
                labels = {f"{movie['title']} · {movie['movie_id']}": movie for movie in seeds}
                selected_label = st.selectbox("Choose a film", list(labels))
                selected = labels[selected_label]
                if st.button("Show similar films", type="primary", key="show_similar"):
                    with st.spinner("Finding films with a similar feel…"):
                        st.session_state["similar_results"] = api.similar_movies(
                            selected["movie_id"]
                        )
                        st.session_state["similar_seed_id"] = selected["movie_id"]
                        st.session_state["similar_seed_title"] = selected["title"]
                if st.session_state.get("similar_seed_id") == selected["movie_id"]:
                    seed_title = st.session_state.get("similar_seed_title", "that film")
                    st.caption(f"Because you chose {seed_title}")
                    show_cards(
                        st.session_state["similar_results"],
                        key="similar",
                        user_id=user_id,
                        api=api,
                    )
            else:
                st.info("No titles match that search yet.")
        except APIError as error:
            st.error(str(error))
    else:
        st.info("Choose a movie you already love and we’ll find its cinematic cousins.")
