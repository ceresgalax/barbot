import asyncio
import base64
import concurrent.futures
import folium
from selenium import webdriver
import time
from typing import List, Tuple, TypeAlias, Dict, cast

from . import app, bars

LatLon: TypeAlias = Tuple[float, float]

MAP_PADDING = 0.005  # measured in lat/lon


def _get_bounds(coordinates: List[LatLon], padding: float) -> Tuple[LatLon, LatLon]:
    latmin = min([c[0] for c in coordinates]) - padding
    latmax = max([c[0] for c in coordinates]) + padding
    lonmin = min([c[1] for c in coordinates]) - padding
    lonmax = max([c[1] for c in coordinates]) + padding
    return ((latmin, lonmin), (latmax, lonmax))


def _get_center(coordinates: List[LatLon]) -> LatLon:
    lat = sum(c[0] for c in coordinates) / len(coordinates)
    lon = sum(c[1] for c in coordinates) / len(coordinates)
    return (lat, lon)


def _render_html(html: str) -> bytes:
    html_base64 = base64.b64encode(html.encode("utf-8")).decode()
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    driver = webdriver.Remote(command_executor=app.SELENIUM_SERVER_URL, options=options)
    try:
        driver.get("data:text/html;base64," + html_base64)
        driver.fullscreen_window()
        time.sleep(2)  # let the map adjust to initial render
        div = driver.find_element("class name", "folium-map")
        png = div.screenshot_as_png
    except:
        raise
    finally:
        driver.quit()
    return png


def _map_bars_to_png(
    bars: List[bars.Bar], dimensions: Tuple[int, int]
) -> Tuple[Dict[str, bars.Bar], bytes]:
    if not bars:
        return {}, bytes()
    coordinates = [(b.latitude, b.longitude) for b in bars]
    folium_map = folium.Map(
        location=_get_center(coordinates), width=dimensions[0], height=dimensions[1]
    )
    # please please please let us never have more than 26 bars
    letter_map = {}
    for index, coordinate in enumerate(coordinates):
        letter = chr(ord("a") + index)
        letter_map[letter.upper()] = bars[index]
        folium.Marker(
            location=coordinate,
            icon=folium.Icon(icon=letter, prefix="fa"),
        ).add_to(folium_map)
    folium.FitBounds(_get_bounds(coordinates, MAP_PADDING)).add_to(folium_map)
    html = folium_map.get_root().render()
    return (letter_map, _render_html(cast(str, html)))


async def map_bars_to_png(
    bars: List[bars.Bar], dimensions: Tuple[int, int]
) -> Tuple[Dict[str, bars.Bar], bytes]:
    # selenium doing some serious blocking work here, so we run it in another thread
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return await asyncio.get_running_loop().run_in_executor(
            pool, _map_bars_to_png, bars, dimensions
        )
