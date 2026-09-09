"""Задача 2: геокодирование адресов через Nominatim (OpenStreetMap) с локальным
кэшем и пометкой ненадёжных результатов для ручной проверки.

Кэш хранится в JSON-файле (по умолчанию delivery_route/cache/geocode_cache.json)
и переживает запуски скрипта, чтобы не геокодировать один и тот же адрес каждый
день заново.

Публичный Nominatim просит: не больше 1 запроса в секунду и осмысленный
User-Agent с контактом — задайте свой через переменную окружения
GEOCODER_USER_AGENT или аргумент --user-agent, если планируете гонять скрипт
часто (см. https://operations.osmfoundation.org/policies/nominatim/).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

import requests

from delivery_route.models import Stop

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = "hyde-courier-route-planner/1.0 (set GEOCODER_USER_AGENT to your contact)"
DEFAULT_CITY_HINT = "Санкт-Петербург, Россия"
MIN_REQUEST_INTERVAL_SEC = 1.1

# Классы/типы результатов Nominatim, которые сами по себе означают "неточный
# адрес" (аналог google-овского "subpremise" — слишком общий объект, а не
# конкретное здание/дом).
UNRELIABLE_TYPES = {
    "administrative",
    "suburb",
    "neighbourhood",
    "quarter",
    "city",
    "town",
    "village",
    "residential",
    "yes",
}


@dataclass
class GeocodeResult:
    lat: float
    lon: float
    display_name: str
    osm_class: str
    osm_type: str
    importance: float = 0.0
    has_house_number: bool = False
    source: str = "nominatim"  # "nominatim" | "manual" | "cache"
    needs_review: bool = False
    note: str = ""


@dataclass
class GeocodeCache:
    path: str
    data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "GeocodeCache":
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        return cls(path=path, data=data)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, self.path)

    def get(self, key: str) -> dict | None:
        return self.data.get(key)

    def set(self, key: str, entry: dict) -> None:
        self.data[key] = entry
        self.save()


def _address_has_house_number(address_raw: str) -> bool:
    import re

    return bool(re.search(r"\d", address_raw))


def _looks_reliable(result_json: dict, address_raw: str) -> tuple[bool, str]:
    osm_class = result_json.get("class", "")
    osm_type = result_json.get("type", "")
    address = result_json.get("address", {})
    has_house_number = bool(address.get("house_number"))
    importance = float(result_json.get("importance", 0) or 0)

    if osm_type in UNRELIABLE_TYPES or osm_class in {"boundary", "place"} and not has_house_number:
        return False, f"неточный тип объекта в OSM: class={osm_class}, type={osm_type}"

    if _address_has_house_number(address_raw) and not has_house_number:
        return False, "в адресе указан номер дома, но Nominatim не подтвердил номер дома"

    if importance and importance < 0.25:
        return False, f"низкая уверенность геокодера (importance={importance:.2f})"

    return True, ""


def query_nominatim(
    address_raw: str,
    session: requests.Session,
    user_agent: str,
    city_hint: str = DEFAULT_CITY_HINT,
) -> GeocodeResult | None:
    query = address_raw if city_hint.lower() in address_raw.lower() else f"{address_raw}, {city_hint}"
    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 1,
        "countrycodes": "ru",
    }
    headers = {"User-Agent": user_agent}
    try:
        resp = session.get(NOMINATIM_URL, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        results = resp.json()
    except (requests.RequestException, ValueError) as exc:
        return GeocodeResult(
            lat=0.0,
            lon=0.0,
            display_name="",
            osm_class="",
            osm_type="",
            needs_review=True,
            note=f"ошибка сети/геокодера: {exc}",
            source="error",
        )

    if not results:
        return GeocodeResult(
            lat=0.0,
            lon=0.0,
            display_name="",
            osm_class="",
            osm_type="",
            needs_review=True,
            note="геокодер не нашёл адрес",
            source="error",
        )

    top = results[0]
    reliable, reason = _looks_reliable(top, address_raw)
    return GeocodeResult(
        lat=float(top["lat"]),
        lon=float(top["lon"]),
        display_name=top.get("display_name", ""),
        osm_class=top.get("class", ""),
        osm_type=top.get("type", ""),
        importance=float(top.get("importance", 0) or 0),
        has_house_number=bool(top.get("address", {}).get("house_number")),
        needs_review=not reliable,
        note=reason,
        source="nominatim",
    )


def osm_check_url(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"


def _prompt_manual_confirmation(stop: Stop, result: GeocodeResult) -> GeocodeResult:
    print("\n--- Требуется проверка координат ---")
    print(f"Адрес: {stop.address_raw}")
    if result.lat and result.lon:
        print(f"Найдено геокодером: {result.lat}, {result.lon} ({result.display_name})")
        print(f"Причина сомнений: {result.note}")
        print(f"Проверить на карте: {osm_check_url(result.lat, result.lon)}")
        prompt = "Подтвердить? [Enter = да, 'lat,lon' = исправить, 's' = пропустить точку]: "
    else:
        print(f"Геокодер не смог определить координаты ({result.note}).")
        prompt = "Введите координаты вручную как 'lat,lon' или 's' чтобы пропустить: "

    try:
        answer = input(prompt).strip()
    except EOFError:
        answer = ""

    if answer.lower() in ("s", "skip", "пропустить"):
        result.needs_review = True
        result.note = (result.note + "; " if result.note else "") + "пропущено пользователем"
        return result

    if answer:
        try:
            lat_str, lon_str = answer.split(",")
            result.lat = float(lat_str.strip())
            result.lon = float(lon_str.strip())
            result.needs_review = False
            result.source = "manual"
            result.note = "координаты введены вручную"
            return result
        except ValueError:
            print("Не удалось разобрать координаты, оставляю как 'требует проверки'.")
            return result

    if result.lat and result.lon:
        result.needs_review = False
        result.source = result.source + "+confirmed"
        result.note = (result.note + "; " if result.note else "") + "подтверждено пользователем"
    return result


def geocode_stops(
    stops: list[Stop],
    cache_path: str = "delivery_route/cache/geocode_cache.json",
    interactive: bool = True,
    user_agent: str | None = None,
    city_hint: str = DEFAULT_CITY_HINT,
) -> list[Stop]:
    """Геокодирует все точки, используя и пополняя локальный кэш.

    Мутирует и возвращает тот же список Stop с заполненными lat/lon/needs_review.
    """

    user_agent = user_agent or os.environ.get("GEOCODER_USER_AGENT", DEFAULT_USER_AGENT)
    cache = GeocodeCache.load(cache_path)
    session = requests.Session()
    last_request_ts = 0.0

    for stop in stops:
        key = stop.address_normalized
        cached = cache.get(key)

        if cached and not cached.get("needs_review"):
            stop.lat = cached["lat"]
            stop.lon = cached["lon"]
            stop.needs_review = False
            stop.geocode_note = "из кэша"
            continue

        if cached:
            result = GeocodeResult(**{**cached, "source": cached.get("source", "cache")})
        else:
            elapsed = time.monotonic() - last_request_ts
            if elapsed < MIN_REQUEST_INTERVAL_SEC:
                time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)
            result = query_nominatim(stop.address_raw, session, user_agent, city_hint)
            last_request_ts = time.monotonic()

        if result.needs_review and interactive:
            result = _prompt_manual_confirmation(stop, result)

        stop.lat = result.lat or None
        stop.lon = result.lon or None
        stop.needs_review = result.needs_review
        stop.geocode_note = result.note

        cache.set(
            key,
            {
                "lat": result.lat,
                "lon": result.lon,
                "display_name": result.display_name,
                "osm_class": result.osm_class,
                "osm_type": result.osm_type,
                "importance": result.importance,
                "has_house_number": result.has_house_number,
                "source": result.source,
                "needs_review": result.needs_review,
                "note": result.note,
                "address_raw": stop.address_raw,
            },
        )

    return stops
