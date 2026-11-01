# CineNova Bridge

A serverless/static catalog-feed builder for an Android movie app. GitHub Actions runs the Python importer and commits `public/catalog.json`; the Android app downloads that JSON directly from GitHub Raw. No VPS or always-on backend is required.

## Supported catalog categories
- Movies
- TV series
- Anime
- TV channels (metadata and authorized public stream references only)
- Banners/posters/backdrops
- Ratings and review data when the configured source actually provides them
- Seasons and episode metadata when the source provides them

**Important:** this project imports catalog metadata. It does not extract hidden video URLs, DRM-protected streams, login cookies, private tokens, or bypass access controls. TV playback must use a stream that you are authorized to distribute. A review is shown as a real review only when it is actually returned by a configured review source; otherwise show rating/review count or "No reviews yet", never fabricated reviews.

## Setup
1. Configure a permitted JSON API or public HTML page in `sources.json` (copy `sources.example.json`).
2. Push the file to this repository.
3. GitHub Actions → **Build catalog feed** → Run workflow. It also runs daily.
4. App feed URL: `https://raw.githubusercontent.com/Imanshu999/Bridge/main/public/catalog.json`

For a private repository, raw feed access may require authentication and should not embed a personal access token in a public APK. Make the repository/feed public if you want a no-login app feed, and only publish metadata you are allowed to republish.

## JSON source configuration
```json
{
  "name": "permitted-catalog",
  "kind": "json",
  "url": "https://catalog.example.org/api/catalog",
  "items_path": "results",
  "fields": {
    "id": "id", "title": "title", "type": "type",
    "year": "year", "overview": "overview",
    "poster": "poster", "backdrop": "backdrop", "banner": "banner",
    "genres": "genres", "rating": "rating",
    "review_count": "review_count", "reviews": "reviews",
    "release_date": "release_date", "detail_url": "url",
    "seasons": "seasons", "episodes": "episodes",
    "channel_number": "number", "language": "language",
    "country": "country", "logo": "logo",
    "authorized_stream_url": "authorized_stream_url"
  }
}
```

For HTML sources use `kind: "html"` with `selectors.item` and CSS selectors for fields. Attribute syntax is `img.poster@src`, `a.details@href`. HTML extraction depends on each site's layout and must be configured per source.

## Android contract
Each record is normalized with a stable `id`, `type`, `title`, artwork URLs, metadata, optional seasons/episodes, optional real reviews and TV-channel fields. Use the same `id` to bind artwork, details, search results and the selected playback-provider result. Do not assume a banner image is a playable movie.

## No fake data
The initial catalog is intentionally empty. It is not populated with sample/fake movie records. Reviews, ratings, banners and channels only appear when returned by the configured source.

## Local run
```bash
pip install -r requirements.txt
cp sources.example.json sources.json
python scraper.py --config sources.json --output public/catalog.json
```
