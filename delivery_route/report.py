"""Задача 5: формирование итогового отчёта — ссылка на Яндекс.Навигатор,
список точек сверх лимита, итоговые км/время, текстовый список всех точек
с комментариями."""

from __future__ import annotations

from delivery_route.limiter import SplitResult
from delivery_route.models import Stop

KIND_LABELS = {
    "start": "СТАРТ (склад)",
    "pickup": "ПИКАП",
    "delivery": "Доставка",
    "finish": "ФИНИШ (возврат на склад)",
}


def yandex_navi_link(points: list[Stop]) -> str:
    coords = "~".join(f"{p.lat},{p.lon}" for p in points)
    return f"https://yandex.ru/navi?rtext={coords}&rtt=auto"


def _fmt_km(km: float) -> str:
    return f"{km:.1f} км"


def _fmt_hours(hours: float) -> str:
    h = int(hours)
    m = round((hours - h) * 60)
    if m == 60:
        h += 1
        m = 0
    return f"{h} ч {m:02d} мин"


def build_report_text(
    full_route: list[Stop],
    split: SplitResult,
    optimize_method: str,
    unresolved_stops: list[Stop] | None = None,
    max_km: float = 70.0,
    max_hours: float = 4.0,
) -> str:
    unresolved_stops = unresolved_stops or []
    lines: list[str] = []

    lines.append("=" * 70)
    lines.append("МАРШРУТНЫЙ ЛИСТ — итог построения маршрута")
    lines.append("=" * 70)

    method_names = {
        "osrm_trip": "OSRM Trip API (точное решение TSP)",
        "heuristic_table": "эвристика (ближайший сосед + 2-opt) на матрице OSRM Table API",
        "original_order": "OSRM недоступен — точки развоза оставлены в исходном порядке!",
        "trivial": "точек развоза нет",
    }
    lines.append(f"Способ оптимизации порядка развоза: {method_names.get(optimize_method, optimize_method)}")
    if split.is_estimated:
        lines.append(
            "⚠ OSRM Route API был недоступен — км и время ниже посчитаны ПРИБЛИЗИТЕЛЬНО "
            "(по прямой с поправкой на дороги), а не по реальным дорогам."
        )
    lines.append("")

    main_progress = split.progress[: len(split.main_route)]
    full_progress = split.progress
    main_km = main_progress[-1].cumulative_km if main_progress else 0.0
    main_h = main_progress[-1].cumulative_hours if main_progress else 0.0
    full_km = full_progress[-1].cumulative_km if full_progress else 0.0
    full_h = full_progress[-1].cumulative_hours if full_progress else 0.0

    lines.append("--- ИТОГОВЫЕ ЦИФРЫ ---")
    lines.append(f"Лимит: {max_km:.0f} км ИЛИ {max_hours:.0f} ч (что наступит раньше)")
    lines.append(f"Основной маршрут (в пределах лимита): {_fmt_km(main_km)}, {_fmt_hours(main_h)}")
    lines.append(f"Полный маршрут (если ехать все точки):  {_fmt_km(full_km)}, {_fmt_hours(full_h)}")
    if split.cut_reason:
        reason = "пробегу (70 км)" if split.cut_reason == "distance" else "времени (4 ч)"
        lines.append(f"Обрезка сработала по: {reason}")
    else:
        lines.append("Лимит не превышен — весь маршрут укладывается в оплаченный объём.")
    lines.append("")

    lines.append("--- ССЫЛКА НА ЯНДЕКС.НАВИГАТОР (только основной маршрут) ---")
    lines.append(yandex_navi_link(split.main_route))
    lines.append("")

    if split.excess_points:
        lines.append("--- ТОЧКИ СВЕРХ ЛИМИТА (не входят в оплаченный объём) ---")
        for stop in split.excess_points:
            label = KIND_LABELS.get(stop.kind, stop.kind)
            lines.append(
                f"  [{label}] {stop.display_address()} — {stop.total_weight_kg:.0f} кг, "
                f"{stop.total_boxes:.0f} кор. (заказы: {', '.join(stop.order_numbers) or '-'})"
            )
        lines.append("")
    else:
        lines.append("--- ТОЧЕК СВЕРХ ЛИМИТА НЕТ ---")
        lines.append("")

    lines.append("--- ПОЛНЫЙ СПИСОК ТОЧЕК МАРШРУТА (с комментариями) ---")
    main_ids = {id(s) for s in split.main_route}
    for i, p in enumerate(full_progress):
        stop = p.stop
        label = KIND_LABELS.get(stop.kind, stop.kind)
        in_main = id(stop) in main_ids
        status = "" if in_main else "  <-- СВЕРХ ЛИМИТА"
        lines.append(
            f"{i:>2}. [{label}] {stop.display_address()}{status}\n"
            f"      нарастающий пробег: {_fmt_km(p.cumulative_km)}, "
            f"нарастающее время: {_fmt_hours(p.cumulative_hours)}"
        )
        if stop.orders:
            lines.append(
                f"      вес: {stop.total_weight_kg:.0f} кг, коробок: {stop.total_boxes:.0f}, "
                f"заказы: {', '.join(stop.order_numbers)}"
            )
        if stop.comment:
            lines.append(f"      комментарий: {stop.comment}")
        if stop.needs_review:
            lines.append(f"      ⚠ координаты требуют проверки: {stop.geocode_note}")
    lines.append("")

    if unresolved_stops:
        lines.append("--- ТОЧКИ БЕЗ ПОДТВЕРЖДЁННЫХ КООРДИНАТ (не включены в маршрут!) ---")
        for stop in unresolved_stops:
            lines.append(
                f"  {stop.display_address()} — {stop.total_weight_kg:.0f} кг "
                f"(заказы: {', '.join(stop.order_numbers) or '-'}); причина: {stop.geocode_note}"
            )
        lines.append("Нужно проверить/задать координаты вручную и запустить расчёт заново.")
        lines.append("")

    return "\n".join(lines)
