from urllib.parse import urlsplit

from .utils import Cache, Time, get_logger, leagues, network

log = get_logger(__name__)

urls: dict[str, dict[str, str | float]] = {}

TAG = "XYZ2"

CACHE_FILE = Cache(TAG, exp=19_800)

API_URL = "https://tsnusopen.bobbbyb02.workers.dev"


async def get_events() -> dict[str, dict[str, str | float]]:
    now = Time.rn()

    events = {}

    if not (api_req := await network.request(API_URL, log=log)):
        return events

    api_data = api_req.json()

    if not api_data.get("success"):
        return events

    for game in api_data.get("events", []):
        title, stream_url = game.get("title"), game.get("embedUrl")

        if not (title and stream_url):
            continue

        splits = urlsplit(stream_url)

        if not (stream_id := splits.query):
            continue

        sport, event_name = (s.strip() for s in title.split("-", 1))

        key = f"[{sport}] {event_name} ({TAG})"

        tvg_id, logo = leagues.get_tvg_info(sport, event_name)

        events[key] = {
            "url": f"https://iptvstream2.xyzstreams.space/{stream_id}/mono.ts.m3u8",
            "logo": game.get("thumbnail") or logo,
            "base": API_URL,
            "timestamp": now.timestamp(),
            "id": tvg_id or "Live.Event.us",
        }

    return events


async def scrape() -> None:
    if cached := CACHE_FILE.load():
        urls.update(cached)

        log.info(f"Loaded {len(urls)} event(s) from cache")

        return

    log.info(f'Scraping from "{API_URL}"')

    urls.update(await get_events())

    log.info(f"Collected and cached {len(urls)} new event(s)")

    CACHE_FILE.write(urls)
