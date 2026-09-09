"""CLI: python -m delivery_route.cli --xlsx маршрутный_лист.xlsx [--pickup "адрес"]...

Собирает вместе все задачи:
  1. чтение маршрутного листа (parse_route_sheet)
  2. геокодирование с кэшем (geocode)
  3. построение маршрута: старт -> пикапы -> оптимизированный развоз -> финиш (route_builder)
  4. обрезка по лимиту 70 км / 4 ч (limiter)
  5. отчёт: ссылка на Яндекс.Навигатор, точки сверх лимита, итоговые км/время (report)
"""

from __future__ import annotations

import argparse
import sys

import requests

from delivery_route.geocode import geocode_stops
from delivery_route.limiter import DEFAULT_MAX_HOURS, DEFAULT_MAX_KM, split_route_by_limit
from delivery_route.models import Stop
from delivery_route.parse_route_sheet import load_stops_from_xlsx
from delivery_route.report import build_report_text
from delivery_route.route_builder import build_full_route

DEFAULT_WAREHOUSE_LABEL = "пр. Большевиков, 42к2В (склад)"
DEFAULT_WAREHOUSE_LAT = 59.889070
DEFAULT_WAREHOUSE_LON = 30.491275


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Расчёт и обрезка маршрута доставки")
    parser.add_argument("--xlsx", required=True, help="Путь к маршрутному листу (xlsx)")
    parser.add_argument("--sheet", default=None, help="Имя листа в xlsx (по умолчанию — первый)")
    parser.add_argument(
        "--pickup",
        action="append",
        default=[],
        help="Обязательная точка-пикап в начале маршрута (адрес). "
        "Можно указать несколько раз, порядок = порядок в маршруте.",
    )
    parser.add_argument(
        "--cache-path",
        default="delivery_route/cache/geocode_cache.json",
        help="Файл кэша геокодирования",
    )
    parser.add_argument("--max-km", type=float, default=DEFAULT_MAX_KM)
    parser.add_argument("--max-hours", type=float, default=DEFAULT_MAX_HOURS)
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Не спрашивать подтверждение неточных координат (просто пометить и исключить из маршрута)",
    )
    parser.add_argument("--user-agent", default=None, help="User-Agent для запросов к Nominatim")
    parser.add_argument("--output", default=None, help="Куда сохранить текстовый отчёт (по умолчанию — только stdout)")
    parser.add_argument("--start-lat", type=float, default=DEFAULT_WAREHOUSE_LAT)
    parser.add_argument("--start-lon", type=float, default=DEFAULT_WAREHOUSE_LON)
    parser.add_argument("--start-label", default=DEFAULT_WAREHOUSE_LABEL)
    return parser.parse_args(argv)


def _make_fixed_stop(kind: str, label: str, lat: float, lon: float) -> Stop:
    return Stop(
        address_raw=label,
        address_normalized=label.lower(),
        lat=lat,
        lon=lon,
        needs_review=False,
        kind=kind,
        label=label,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        stops = load_stops_from_xlsx(args.xlsx, sheet_name=args.sheet)
    except Exception as exc:  # noqa: BLE001 — верхнеуровневая защита от падения скрипта
        print(f"Не удалось прочитать маршрутный лист: {exc}", file=sys.stderr)
        return 1

    if not stops:
        print("В маршрутном листе не найдено ни одного заказа.", file=sys.stderr)
        return 1

    pickup_stops = [
        Stop(address_raw=addr, address_normalized=addr.lower(), kind="pickup", label=addr)
        for addr in args.pickup
    ]

    to_geocode = pickup_stops + stops
    geocode_stops(
        to_geocode,
        cache_path=args.cache_path,
        interactive=not args.non_interactive,
        user_agent=args.user_agent,
    )

    start = _make_fixed_stop("start", args.start_label, args.start_lat, args.start_lon)
    finish = _make_fixed_stop("finish", args.start_label, args.start_lat, args.start_lon)

    for p in pickup_stops:
        if p.lat is None or p.lon is None:
            print(
                f"Пикап '{p.address_raw}' не удалось геокодировать — маршрут без координат "
                "обязательной точки построить нельзя.",
                file=sys.stderr,
            )
            return 1

    resolved = [s for s in stops if s.lat is not None and s.lon is not None]
    unresolved = [s for s in stops if s.lat is None or s.lon is None]
    for s in resolved:
        s.kind = "delivery"

    session = requests.Session()
    full_route, method = build_full_route(start, pickup_stops, resolved, finish, session=session)
    split = split_route_by_limit(full_route, session=session, max_km=args.max_km, max_hours=args.max_hours)

    report_text = build_report_text(
        full_route,
        split,
        method,
        unresolved_stops=unresolved,
        max_km=args.max_km,
        max_hours=args.max_hours,
    )
    print(report_text)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"\nОтчёт сохранён в {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
