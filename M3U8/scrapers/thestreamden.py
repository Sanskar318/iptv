from collections.abc import KeysView
from functools import partial
from urllib.parse import urljoin

from playwright.async_api import Browser
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from .utils import Cache, Event, Time, get_logger, leagues, network

log = get_logger(__name__)

urls: dict[str, dict[str, str | float]] = {}

TAG = "STRMDEN"

CACHE_FILE = Cache(TAG, exp=10_800)

BASE_URL = "https://thestreamden.com/"


async def get_events(cached_keys: KeysView[str]) -> list[Event]:
    events: list[Event] = []

    if not (
        html_data := await network.request(
            BASE_URL,
            params={"live_only": 1},
            log=log,
        )
    ):
        return events

    soup = HTMLParser(html_data.content)

    sport = "Live Event"

    for card in soup.css(".game-card.live"):
        if not all(
            values := [
                card.css_first(x)
                for x in (
                    ".game-title",
                    ".game-title > a",
                    ".meta > span.streams",
                )
            ]
        ):
            continue

        event_name_elem, href_elem, streams_elem = values

        if streams_elem.text(strip=True) == "1 stream":
            continue

        elif not (href := href_elem.attributes.get("href")):
            continue

        if sport_elem := (
            card.css_first(".game-tags-row > .game-tags > span.tag-pill.outline")
            or card.css_first(".game-tags-row > .game-tags > span.tag-pill")
        ):
            sport = sport_elem.text(strip=True)

        event_name = event_name_elem.text(strip=True)

        game_id = href.split("/")[-1]

        if f"[{sport}] {event_name} ({TAG})" in cached_keys:
            continue

        events.append(
            Event(
                sport=sport,
                name=event_name,
                link=urljoin(BASE_URL, f"api/v1/play/{game_id}"),
            )
        )

    return events


async def scrape(browser: Browser) -> None:
    cached_urls = CACHE_FILE.load()

    valid_urls = {k: v for k, v in cached_urls.items() if v["source"]}

    valid_count = cached_count = len(valid_urls)

    urls.update(valid_urls)

    log.info(f"Loaded {cached_count} event(s) from cache")

    log.info(f'Scraping from "{BASE_URL}"')

    if events := await get_events(cached_urls.keys()):
        log.info(f"Processing {len(events)} new URL(s)")

        now = Time.rn()

        async with network.event_context(browser) as context:
            for i, ev in enumerate(events, start=1):
                async with network.event_page(context) as page:
                    handler = partial(
                        network.process_event,
                        url=ev.link,
                        url_num=i,
                        page=page,
                        log=log,
                    )

                    source = await network.safe_process(
                        handler,
                        url_num=i,
                        semaphore=network.PW_S,
                        log=log,
                    )

                    tvg_id, logo = leagues.get_tvg_info(ev.sport, ev.name)

                    key = f"[{ev.sport}] {ev.name} ({TAG})"

                    entry = {
                        "source": source,
                        "logo": logo,
                        "refer": ev.link,
                        "timestamp": now.timestamp(),
                        "tvg-id": tvg_id or "Live.Event.us",
                    }

                    cached_urls[key] = entry

                    if source:
                        valid_count += 1

                        urls[key] = entry

        log.info(f"Collected and cached {valid_count - cached_count} new event(s)")

    else:
        log.info("No new events found")

    CACHE_FILE.write(cached_urls)
