# CineNova app data contract

The app should consume one normalized JSON document from:

`https://raw.githubusercontent.com/Imanshu999/Bridge/main/public/catalog.json`

## App sections and required fields

### Home
- Hero carousel: `banner_url` or `backdrop_url`, title, short overview, type, year, rating, stable `id`.
- Rows: Trending, Recently Added, Movies, Series, Anime, Live TV, Continue Watching, Top Rated.
- Do not render an empty row as if it contains content.

### Movie details
- title, poster, backdrop/banner, overview, genres, release date/year, rating, review count, actual reviews, detail URL.
- Cast, director, runtime, age rating and languages should be added when a source provides them.

### Series and anime
- Seasons and episodes, episode number, episode title, synopsis, still image, duration and release date when available.
- Anime may additionally have Japanese/original title, season/cour, episode number, audio language and subtitle languages when source data exists.

### Live TV
- channel title, channel number, logo, poster, language, country, category and EPG/programme schedule.
- A playable channel needs a separately verified and authorized stream URL/provider result. Catalog metadata alone is not playback.

### Reviews and ratings
- Display a rating only when the source supplies it, and label its source.
- Display actual review text only when the source returns real review records with author/date/rating.
- Never generate fake user reviews or imply that an imported rating is an app-user rating.
- App-user reviews are a separate feature and need your own user/account storage; this static scraper cannot collect user submissions.

## Data integrity rules
- Use the same stable `id` for home cards, search results, detail page and playback lookup.
- The selected item's artwork and metadata must stay attached to that ID.
- A banner URL is artwork, not a video URL.
- `playback.available=false` means show details but do not show a working Play action.
- Missing data stays null/empty; do not invent cast, ratings, review text, seasons or channels.

## Current feed limitations
The bridge is a metadata importer. It supports configured JSON APIs and selector-based public HTML pages. It is not a universal crawler; every source has its own schema/selectors. JavaScript-only pages may need an official API or a separately implemented compatible parser. No video extraction, DRM bypass, private API token harvesting or access-control circumvention is included.
