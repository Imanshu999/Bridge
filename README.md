# CineNova Bridge

A GitHub Actions-powered metadata catalog builder for an Android app. It writes a static JSON feed to `public/catalog.json`; no VPS or always-on server is needed.

## Real data sources included
- **Movies + TV series + details + banners + credits + real user reviews:** TMDB API.
- **Anime + artwork/banner + synopsis + genres + scores + season/episode counts:** AniList GraphQL API.
- **TV channel names + countries + categories + logos + EPG source references:** iptv-org public API.

The feed does not invent titles, ratings or reviews. If an upstream has no review text, its reviews array remains empty.

## One-time setup
1. In TMDB, create an account and request an API Read Access Token: https://www.themoviedb.org/settings/api
2. In this GitHub repository open **Settings → Secrets and variables → Actions → New repository secret**.
3. Name it exactly `TMDB_API_READ_ACCESS_TOKEN`, paste the TMDB API Read Access Token, and save.
4. Open **Actions → Build live catalog → Run workflow**. The workflow also refreshes every 6 hours.
5. After a successful run, the app reads:
   `https://raw.githubusercontent.com/Imanshu999/Bridge/main/public/catalog.json`

TMDB authentication docs: https://developer.themoviedb.org/docs/authentication-application
TMDB API data/images are free for non-commercial use with attribution; commercial use requires contacting TMDB. Review TMDB's current terms before publishing your app.

## Public app feed
You said you will make this repository public. Do that only after checking that no secrets have been committed. The workflow stores the TMDB token as a GitHub Actions Secret; it is not written into the JSON feed. Never put the token in Android source code or in `sources.json`.

## App data
Each record has a stable `id`, `type`, title, metadata, artwork and source. Movies/series have real TMDB reviews when supplied by TMDB. Anime comes from AniList. TV channels come from iptv-org and include logo and EPG references where available.

## Playback is separate
This feed is metadata, not a movie/video host. Artwork/banner URLs are not playable video URLs. The channel importer deliberately does not copy third-party stream URLs into the app. Add playback only through sources/providers you are authorized to use. `playback.available` is false until the app integrates such a provider.

## Local run
```bash
python -m pip install requests
TMDB_API_READ_ACCESS_TOKEN=your_token python scraper.py
```
AniList and iptv-org do not need API keys.

## India live TV playlist
The catalog builder also imports channel metadata from the official iptv-org India playlist:
`https://iptv-org.github.io/iptv/countries/in.m3u`

It reads each `#EXTINF` record and extracts channel title, tvg-id, logo, group/category and language where provided. The normalized feed includes the original playlist URL so the Android IPTV player can load the source playlist directly. Individual stream URLs are not copied into the catalog; availability and playback can change, and the upstream playlist remains authoritative.

## Movie and series metadata without a TMDB key
The catalog builder also imports movie and series metadata from the public Stremio/Cinemeta catalog endpoint (`https://cinemeta-catalogs.strem.io/top/catalog`). This supplies titles, IMDb IDs, posters, backgrounds/banners, descriptions, genres, ratings and available cast/director metadata. It is a public third-party dependency, not a guaranteed or versioned API; the build validates responses and records source errors. This source does not provide verified user reviews or video playback URLs. TMDB remains an optional additional source for TMDB review data when `TMDB_API_READ_ACCESS_TOKEN` is configured.

AniList import is paginated and continues until the API reports no further anime pages; it is no longer limited to the first 50 results. The import is subject to AniList API availability and rate limits.
