"""Общие структуры данных для модуля построения маршрута."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Order:
    """Один заказ из маршрутного листа (до объединения по адресу)."""

    number: str
    info: str
    extra_info: str
    amount: str
    payment_status: str
    weight_kg: float
    boxes: float
    delivery_person: str
    contact_person: str
    address_raw: str
    date_time: str


@dataclass
class Stop:
    """Точка маршрута после объединения заказов по адресу.

    Несколько заказов на один адрес схлопываются в одну Stop (кг суммируются).
    """

    address_raw: str
    address_normalized: str
    orders: list[Order] = field(default_factory=list)

    lat: float | None = None
    lon: float | None = None
    needs_review: bool = False
    geocode_note: str = ""

    kind: str = "delivery"  # "start" | "pickup" | "delivery" | "finish"
    label: str = ""  # для start/pickup/finish, задаваемых вручную

    @property
    def total_weight_kg(self) -> float:
        return sum(o.weight_kg for o in self.orders)

    @property
    def total_boxes(self) -> float:
        return sum(o.boxes for o in self.orders)

    @property
    def order_numbers(self) -> list[str]:
        return [o.number for o in self.orders]

    @property
    def comment(self) -> str:
        """Текстовый комментарий по времени работы/приёмки для итогового вывода."""
        parts = []
        for o in self.orders:
            bits = [b for b in (o.info, o.extra_info, o.date_time) if b]
            if bits:
                parts.append(" | ".join(bits))
        return "; ".join(parts)

    def display_address(self) -> str:
        return self.label or self.address_raw
