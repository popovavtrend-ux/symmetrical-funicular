"""Обёртка над публичным OSRM API (router.project-osrm.org).

Используются три эндпоинта:
  - Table  — матрица расстояний/времени между точками (для эвристики TSP).
  - Trip   — решение задачи коммивояжёра с фиксированными первой/последней точкой.
  - Route  — реальный маршрут (с км/временем по каждому перегону) для итоговой
             последовательности точек.

Все функции ловят сетевые ошибки и возвращают None вместо падения скрипта —
вызывающий код должен уметь работать с фолбэком.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

OSRM_BASE_URL = "https://router.project-osrm.org"
REQUEST_TIMEOUT_SEC = 30


def _coords_param(points: list[tuple[float, float]]) -> str:
    """points — список (lat, lon). OSRM ждёт "lon,lat;lon,lat;..."."""
    return ";".join(f"{lon},{lat}" for lat, lon in points)


@dataclass
class RouteLeg:
    distance_m: float
    duration_s: float


@dataclass
class RouteResult:
    legs: list[RouteLeg]
    total_distance_m: float
    total_duration_s: float
    geometry: dict | None = None


def get_table(
    points: list[tuple[float, float]], session: requests.Session | None = None
) -> tuple[list[list[float]], list[list[float]]] | None:
    """Возвращает (distances_m, durations_s) — квадратные матрицы NxN, либо None
    при ошибке сети/сервиса."""

    session = session or requests.Session()
    url = f"{OSRM_BASE_URL}/table/v1/driving/{_coords_param(points)}"
    params = {"annotations": "distance,duration"}
    try:
        resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok":
            return None
        return data["distances"], data["durations"]
    except (requests.RequestException, ValueError, KeyError):
        return None


def get_trip(
    points: list[tuple[float, float]],
    session: requests.Session | None = None,
    source: str = "first",
    destination: str = "last",
    roundtrip: bool = False,
) -> list[int] | None:
    """Решает открытую TSP с фиксированными первой/последней точками (если
    source=first, destination=last). Возвращает порядок индексов исходного
    списка points, либо None при ошибке/невозможности решить."""

    session = session or requests.Session()
    url = f"{OSRM_BASE_URL}/trip/v1/driving/{_coords_param(points)}"
    params = {
        "source": source,
        "destination": destination,
        "roundtrip": "true" if roundtrip else "false",
    }
    try:
        resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok":
            return None
        waypoints = data["waypoints"]
        # waypoints[i]["waypoint_index"] — позиция исходной точки i в оптимальном
        # маршруте. Сортировкой исходных индексов по этому значению получаем
        # порядок обхода.
        return sorted(range(len(waypoints)), key=lambda i: waypoints[i]["waypoint_index"])
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None


def get_route(
    points: list[tuple[float, float]], session: requests.Session | None = None
) -> RouteResult | None:
    """Реальный маршрут через заданные точки по порядку. Возвращает суммарную
    дистанцию/время и разбивку по перегонам (leg = участок между соседними
    точками из points)."""

    session = session or requests.Session()
    url = f"{OSRM_BASE_URL}/route/v1/driving/{_coords_param(points)}"
    params = {"overview": "false", "annotations": "false", "steps": "false"}
    try:
        resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        route = data["routes"][0]
        legs = [
            RouteLeg(distance_m=leg["distance"], duration_s=leg["duration"])
            for leg in route["legs"]
        ]
        return RouteResult(
            legs=legs,
            total_distance_m=route["distance"],
            total_duration_s=route["duration"],
        )
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None
