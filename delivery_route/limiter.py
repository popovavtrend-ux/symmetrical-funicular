"""Задача 4: обрезка маршрута по лимиту оплаченного объёма работы.

Нарастающие км и время считаются по всей последовательности точек маршрута
(старт -> обязательные пикапы -> точки развоза -> финиш), т.к. по условиям
пикапы и финиш физически являются частью того же выезда. Как только на
очередной точке нарастающий пробег впервые превышает DEFAULT_MAX_KM или
нарастающее время впервые превышает DEFAULT_MAX_HOURS — эта точка ещё входит
в основной маршрут, а все точки после неё уходят в список "сверх лимита".

Реальные км/время берутся из OSRM Route API (route_builder использует
готовую последовательность точек). Если Route API недоступен (сетевая
ошибка) — используется приблизительная оценка по прямой (haversine) с
поправочным коэффициентом на реальность дорог, и результат явно помечается
как приблизительный, чтобы не выдавать его за точный.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import requests

from delivery_route.models import Stop
from delivery_route.osrm import RouteLeg, RouteResult, get_route

DEFAULT_MAX_KM = 70.0
DEFAULT_MAX_HOURS = 4.0

# Поправочный коэффициент "прямая -> реальная дорога" и средняя скорость в
# городе для fallback-оценки, когда OSRM Route API недоступен.
STRAIGHT_LINE_ROAD_FACTOR = 1.3
FALLBACK_AVG_SPEED_KMH = 22.0


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return r * c


def get_route_or_estimate(
    points: list[Stop], session: requests.Session | None = None
) -> tuple[RouteResult, bool]:
    """Возвращает (RouteResult, is_estimated). is_estimated=True означает, что
    OSRM Route API был недоступен и использована приблизительная оценка."""

    session = session or requests.Session()
    coords = [(p.lat, p.lon) for p in points]
    result = get_route(coords, session=session)
    if result is not None:
        return result, False

    legs = []
    for a, b in zip(points, points[1:]):
        straight_km = _haversine_km(a.lat, a.lon, b.lat, b.lon)
        road_km = straight_km * STRAIGHT_LINE_ROAD_FACTOR
        duration_s = road_km / FALLBACK_AVG_SPEED_KMH * 3600
        legs.append(RouteLeg(distance_m=road_km * 1000, duration_s=duration_s))

    return (
        RouteResult(
            legs=legs,
            total_distance_m=sum(l.distance_m for l in legs),
            total_duration_s=sum(l.duration_s for l in legs),
        ),
        True,
    )


@dataclass
class PointProgress:
    stop: Stop
    cumulative_km: float
    cumulative_hours: float
    leg_km: float
    leg_hours: float


@dataclass
class SplitResult:
    main_route: list[Stop]
    excess_points: list[Stop]
    progress: list[PointProgress]  # по всем точкам, включая начало и финиш
    is_estimated: bool
    cut_reason: str  # "distance" | "time" | "" (если лимит не превышен)


def split_route_by_limit(
    full_route: list[Stop],
    session: requests.Session | None = None,
    max_km: float = DEFAULT_MAX_KM,
    max_hours: float = DEFAULT_MAX_HOURS,
) -> SplitResult:
    route_result, is_estimated = get_route_or_estimate(full_route, session=session)

    progress = [PointProgress(stop=full_route[0], cumulative_km=0.0, cumulative_hours=0.0, leg_km=0.0, leg_hours=0.0)]
    main_route = [full_route[0]]
    excess: list[Stop] = []
    cut_triggered = False
    cut_reason = ""
    cum_km = 0.0
    cum_h = 0.0

    for leg, stop in zip(route_result.legs, full_route[1:]):
        leg_km = leg.distance_m / 1000.0
        leg_h = leg.duration_s / 3600.0
        cum_km += leg_km
        cum_h += leg_h
        progress.append(
            PointProgress(stop=stop, cumulative_km=cum_km, cumulative_hours=cum_h, leg_km=leg_km, leg_hours=leg_h)
        )

        if not cut_triggered:
            main_route.append(stop)
            if cum_km > max_km or cum_h > max_hours:
                cut_triggered = True
                cut_reason = "distance" if cum_km > max_km else "time"
        else:
            excess.append(stop)

    return SplitResult(
        main_route=main_route,
        excess_points=excess,
        progress=progress,
        is_estimated=is_estimated,
        cut_reason=cut_reason,
    )
