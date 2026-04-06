"""Seat matrix helpers for quota-based allocation and waitlist management."""

from __future__ import annotations

from typing import Optional

from irctc_booking.models import BookingStatusEnum, QuotaEnum, QuotaSlot, SeatMatrix


class SeatMatrixManager:
    """Utility methods that mutate seat matrices in a deterministic way."""

    @staticmethod
    def create_seat_matrix(
        train_no: str,
        class_code: str,
        quota_configs: dict[QuotaEnum, dict],
    ) -> SeatMatrix:
        quota_allocations: dict[QuotaEnum, QuotaSlot] = {}
        for quota, cfg in quota_configs.items():
            quota_allocations[quota] = QuotaSlot(
                total_seats=cfg["total_seats"],
                confirmed_seats=cfg["total_seats"],
                waitlist=[],
                fare_base_inr=cfg["fare_base_inr"],
                tatkal_surcharge_pct=cfg.get("tatkal_surcharge_pct", 0.30),
            )

        return SeatMatrix(
            train_no=train_no,
            class_code=class_code,
            quota_allocations=quota_allocations,
        )

    @staticmethod
    def allocate_seat(
        seat_matrix: SeatMatrix,
        quota: QuotaEnum,
        passenger_id: str,
    ) -> tuple[BookingStatusEnum, Optional[int]]:
        if quota not in seat_matrix.quota_allocations:
            raise ValueError(f"Quota {quota.value} not configured")

        slot = seat_matrix.quota_allocations[quota]
        if slot.confirmed_seats > 0:
            slot.confirmed_seats -= 1
            return BookingStatusEnum.CNF, None

        slot.waitlist.append(passenger_id)
        return BookingStatusEnum.WL, len(slot.waitlist)

    @staticmethod
    def promote_waitlist(seat_matrix: SeatMatrix, quota: QuotaEnum) -> Optional[str]:
        slot = seat_matrix.quota_allocations.get(quota)
        if not slot or not slot.waitlist:
            return None
        return slot.waitlist.pop(0)

    @staticmethod
    def cancel_booking(
        seat_matrix: SeatMatrix,
        quota: QuotaEnum,
        passenger_id: str,
        was_confirmed: bool,
    ) -> bool:
        slot = seat_matrix.quota_allocations.get(quota)
        if not slot:
            return False

        if was_confirmed:
            slot.confirmed_seats += 1
            return True

        if passenger_id in slot.waitlist:
            slot.waitlist.remove(passenger_id)
            return True
        return False

    @staticmethod
    def reduce_seats(seat_matrix: SeatMatrix, quota: QuotaEnum, count: int) -> int:
        slot = seat_matrix.quota_allocations.get(quota)
        if not slot or count <= 0:
            return 0
        reduced = min(count, slot.confirmed_seats)
        slot.confirmed_seats -= reduced
        return reduced

    @staticmethod
    def get_fare(
        seat_matrix: SeatMatrix,
        quota: QuotaEnum,
        tatkal_window_open: bool,
    ) -> float:
        slot = seat_matrix.quota_allocations.get(quota)
        if not slot:
            return 0.0

        fare = slot.fare_base_inr
        if quota == QuotaEnum.Tatkal and tatkal_window_open:
            fare *= 1.0 + slot.tatkal_surcharge_pct
        return fare
