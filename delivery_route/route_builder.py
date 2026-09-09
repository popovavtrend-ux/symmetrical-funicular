"""Задача 3: построение маршрута.

Порядок обязательных точек (старт, пикапы) задаётся пользователем и не
меняется. Точки развоза оптимизируются по реальным расстояниям/времени:
сперва пробуем OSRM Trip API (решает задачу коммивояжёра с фиксированными
первой/последней точкой), при недоступности сервиса — эвристика
"ближайший сосед + 2-opt" на матрице расстояний из OSRM Table API.

Время работы/приёмки НЕ влияет на порядок точек — это только комментарий
в итоговом выводе (см. models.Stop.comment).
"""

from __future__ import annotations

import requests

from delivery_route.models import Stop
from delivery_route.osrm import get_table, get_trip


def _nearest_neighbor_2opt(
    dist_matrix: list[list[float]], fixed_first: int = 0, fixed_last: int | None = None
) -> list[int]:
    """Эвристика TSP на готовой матрице расстояний. Первая и последняя точки
    маршрута зафиксированы, порядок остальных — оптимизируется."""

    n = len(dist_matrix)
    if fixed_last is None:
        fixed_last = n - 1
    middle = [i for i in range(n) if i not in (fixed_first, fixed_last)]
    if not middle:
        return [fixed_first, fixed_last]

    unvisited = set(middle)
    order = [fixed_first]
    current = fixed_first
    while unvisited:
        nxt = min(unvisited, key=lambda j: dist_matrix[current][j])
        order.append(nxt)
        unvisited.discard(nxt)
        current = nxt
    order.append(fixed_last)

    def route_length(o: list[int]) -> float:
        return sum(dist_matrix[o[i]][o[i + 1]] for i in range(len(o) - 1))

    improved = True
    while improved:
        improved = False
        for i in range(1, len(order) - 2):
            for j in range(i + 1, len(order) - 1):
                candidate = order[:i] + order[i : j + 1][::-1] + order[j + 1 :]
                if route_length(candidate) + 1e-9 < route_length(order):
                    order = candidate
                    improved = True
    return order


def optimize_delivery_order(
    anchor_start: Stop,
    anchor_finish: Stop,
    delivery_stops: list[Stop],
    session: requests.Session | None = None,
) -> tuple[list[Stop], str]:
    """Возвращает (оптимизированный список delivery_stops, метод).

    method — "osrm_trip", "heuristic_table" или "original_order" (если и OSRM
    Table оказался недоступен — тогда просто исходный порядок, ничего не
    падает).
    """

    session = session or requests.Session()

    if not delivery_stops:
        return [], "trivial"

    all_points = [anchor_start] + delivery_stops + [anchor_finish]
    coords = [(s.lat, s.lon) for s in all_points]

    trip_order = get_trip(coords, session=session, source="first", destination="last")
    if trip_order is not None:
        ordered_all = [all_points[i] for i in trip_order]
        return ordered_all[1:-1], "osrm_trip"

    table = get_table(coords, session=session)
    if table is not None:
        distances, _durations = table
        order_idx = _nearest_neighbor_2opt(distances, fixed_first=0, fixed_last=len(coords) - 1)
        ordered_all = [all_points[i] for i in order_idx]
        return ordered_all[1:-1], "heuristic_table"

    return delivery_stops, "original_order"


def build_full_route(
    start: Stop,
    pickups: list[Stop],
    delivery_stops: list[Stop],
    finish: Stop,
    session: requests.Session | None = None,
) -> tuple[list[Stop], str]:
    """Собирает итоговую последовательность точек:
    старт -> пикапы (в заданном порядке) -> оптимизированный развоз -> финиш.
    """

    session = session or requests.Session()
    anchor_start = pickups[-1] if pickups else start
    optimized_delivery, method = optimize_delivery_order(
        anchor_start, finish, delivery_stops, session=session
    )
    full_route = [start] + pickups + optimized_delivery + [finish]
    return full_route, method
