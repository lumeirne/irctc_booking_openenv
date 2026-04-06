"""Action handlers for IRCTC booking simulator actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from pydantic import ValidationError

from irctc_booking.models import (
    ActionTypeEnum,
    BookingStatusEnum,
    GenderEnum,
    IrctcBookingState,
    Passenger,
    PNRRecord,
    QuotaEnum,
    SeatAvailability,
    TrainInfo,
)
from irctc_booking.sim.seat_matrix import SeatMatrixManager


@dataclass
class ActionResult:
    success: bool
    message: str
    penalty: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)


def _add_violation(state: IrctcBookingState, message: str) -> None:
    state.rule_violations.append(message)


def _tatkal_open(state: IrctcBookingState) -> bool:
    return 10 <= state.time_step <= 16


def _passenger_ids(state: IrctcBookingState) -> List[str]:
    return [f"P{i + 1}" for i in range(len(state.passengers))]


def _generate_pnr(state: IrctcBookingState) -> str:
    serial = len(state.pnr_registry) + 1
    task = state.task_id if state.task_id is not None else 0
    return f"PNR{task}{state.step_count:02d}{serial:03d}"


def _availability_train_list(state: IrctcBookingState, source: str, destination: str) -> List[TrainInfo]:
    return [
        t
        for t in state.train_catalog.values()
        if t.source.lower() == source.lower() and t.destination.lower() == destination.lower()
    ]


def handle_search_trains(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    source = (params.get("source") or state.route_source or "").strip()
    destination = (params.get("destination") or state.route_destination or "").strip()

    if not source or not destination:
        return ActionResult(False, "source and destination are required", penalty=-0.05)

    trains = _availability_train_list(state, source, destination)
    if not trains:
        return ActionResult(True, f"No trains found from {source} to {destination}", data={"trains": []})

    return ActionResult(
        True,
        f"Found {len(trains)} train(s) from {source} to {destination}",
        data={"trains": [t.model_dump() for t in trains]},
    )


def handle_check_availability(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    train_no = (params.get("train_no") or "").strip()
    class_code = (params.get("class_code") or "").strip()
    if not train_no or not class_code:
        return ActionResult(False, "train_no and class_code are required", penalty=-0.05)

    key = f"{train_no}:{class_code}"
    matrix = state.seat_matrix.get(key)
    if not matrix:
        return ActionResult(False, f"No availability for train {train_no}, class {class_code}", penalty=-0.05)

    availabilities: List[SeatAvailability] = []
    for quota, slot in matrix.quota_allocations.items():
        availabilities.append(
            SeatAvailability(
                class_code=class_code,
                quota=quota,
                confirmed_seats=slot.confirmed_seats,
                waitlist_count=len(slot.waitlist),
                fare_inr=SeatMatrixManager.get_fare(matrix, quota, _tatkal_open(state)),
            )
        )

    return ActionResult(
        True,
        f"Availability fetched for train {train_no}, class {class_code}",
        data={"availability": [a.model_dump() for a in availabilities]},
    )


def handle_select_train(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    train_no = (params.get("train_no") or "").strip()
    class_code = (params.get("class_code") or "").strip()
    if not train_no or not class_code:
        return ActionResult(False, "train_no and class_code are required", penalty=-0.05)

    key = f"{train_no}:{class_code}"
    if key not in state.seat_matrix:
        return ActionResult(False, f"Train {train_no} with class {class_code} is unavailable", penalty=-0.05)

    state.selected_train = train_no
    state.selected_class = class_code
    return ActionResult(True, f"Selected train {train_no}, class {class_code}")


def handle_add_passenger(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    raw = {
        "name": params.get("name"),
        "age": params.get("age"),
        "gender": params.get("gender"),
        "concession": params.get("concession"),
    }

    try:
        passenger = Passenger(**raw)
    except ValidationError as exc:
        _add_violation(state, "invalid add_passenger payload")
        return ActionResult(False, f"Invalid passenger payload: {exc.errors()[0]['msg']}", penalty=-0.10)

    state.passengers.append(passenger)
    return ActionResult(True, f"Passenger {passenger.name} added")


def handle_apply_quota(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    quota_raw = params.get("quota")
    try:
        quota = QuotaEnum(quota_raw)
    except Exception:
        _add_violation(state, "invalid quota")
        return ActionResult(False, f"Invalid quota {quota_raw}", penalty=-0.05)

    if quota == QuotaEnum.Tatkal and not _tatkal_open(state):
        _add_violation(state, "tatkal applied outside window")
        return ActionResult(False, "Tatkal is available only in steps 10-16", penalty=-0.10)

    if quota == QuotaEnum.Ladies:
        if any(p.gender != GenderEnum.Female for p in state.passengers):
            _add_violation(state, "ladies quota eligibility failure")
            return ActionResult(False, "Ladies quota requires all passengers to be female", penalty=-0.15)

    if quota == QuotaEnum.Senior_Citizen:
        if not any(p.age >= 60 for p in state.passengers):
            _add_violation(state, "senior quota eligibility failure")
            return ActionResult(False, "Senior_Citizen quota needs at least one passenger age 60+", penalty=-0.15)

    state.applied_quota = quota
    return ActionResult(True, f"Applied quota {quota.value}")


def _has_better_confirmed_option(state: IrctcBookingState, current_cost: float) -> bool:
    pax_count = len(state.passengers)
    tatkal_open = _tatkal_open(state)
    for matrix in state.seat_matrix.values():
        for quota, slot in matrix.quota_allocations.items():
            if slot.confirmed_seats < pax_count:
                continue
            alt_cost = SeatMatrixManager.get_fare(matrix, quota, tatkal_open) * pax_count
            if alt_cost <= state.budget_remaining and alt_cost <= current_cost:
                return True
    return False


def handle_book_ticket(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    del params
    if not state.selected_train or not state.selected_class:
        _add_violation(state, "book_ticket before select_train")
        return ActionResult(False, "Call select_train before book_ticket", penalty=-0.15)

    if not state.passengers:
        _add_violation(state, "book_ticket without passengers")
        return ActionResult(False, "No passengers in booking", penalty=-0.10)

    quota = state.applied_quota or QuotaEnum.General
    key = f"{state.selected_train}:{state.selected_class}"
    matrix = state.seat_matrix.get(key)
    if not matrix:
        return ActionResult(False, "Selected train/class no longer available", penalty=-0.05)

    if quota not in matrix.quota_allocations:
        _add_violation(state, "quota unavailable for class")
        return ActionResult(False, f"Quota {quota.value} not available for selected class", penalty=-0.05)

    if quota == QuotaEnum.Ladies and any(p.gender != GenderEnum.Female for p in state.passengers):
        _add_violation(state, "ladies quota booking mismatch")
        return ActionResult(False, "Ladies quota cannot include male passengers", penalty=-0.15)

    tatkal_open = _tatkal_open(state)
    fare_per_pax = SeatMatrixManager.get_fare(matrix, quota, tatkal_open)
    total_cost = fare_per_pax * len(state.passengers)
    if total_cost > state.budget_remaining:
        _add_violation(state, "booking exceeds budget")
        return ActionResult(
            False,
            f"Booking cost {total_cost:.2f} exceeds budget {state.budget_remaining:.2f}",
            penalty=-0.10,
        )

    statuses: List[BookingStatusEnum] = []
    wl_positions: List[int] = []
    passengers = _passenger_ids(state)

    for passenger_id in passengers:
        status, wl_pos = SeatMatrixManager.allocate_seat(matrix, quota, passenger_id)
        statuses.append(status)
        if wl_pos is not None:
            wl_positions.append(wl_pos)

    booking_status = BookingStatusEnum.CNF if all(s == BookingStatusEnum.CNF for s in statuses) else BookingStatusEnum.WL
    waitlist_position = max(wl_positions) if wl_positions else None
    pnr = _generate_pnr(state)

    state.pnr_registry[pnr] = PNRRecord(
        pnr=pnr,
        train_no=state.selected_train,
        class_code=state.selected_class,
        quota=quota,
        passengers=passengers,
        booking_status=booking_status,
        waitlist_position=waitlist_position,
        fare_paid=0.0,
    )
    state.pnr = pnr
    state.booking_status = booking_status
    state.waitlist_position = waitlist_position

    penalty = 0.0
    if booking_status == BookingStatusEnum.WL and _has_better_confirmed_option(state, total_cost):
        penalty = -0.10

    status_text = "CNF" if booking_status == BookingStatusEnum.CNF else f"WL{waitlist_position}"
    return ActionResult(
        True,
        f"Booked ticket. PNR {pnr}, status {status_text}. Pay to confirm transaction.",
        penalty=penalty,
        data={"pnr": pnr, "fare": total_cost, "status": booking_status.value},
    )


def handle_pay(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    pnr = params.get("pnr") or state.pnr
    if not pnr:
        return ActionResult(False, "No PNR selected for payment", penalty=-0.05)

    record = state.pnr_registry.get(pnr)
    if not record:
        return ActionResult(False, f"PNR {pnr} not found", penalty=-0.05)

    if record.fare_paid > 0:
        return ActionResult(False, f"PNR {pnr} is already paid", penalty=-0.05)

    if (
        state.task_id == 2
        and state.payment_failure_step is not None
        and state.step_count == state.payment_failure_step
        and state.payment_failure_train_no
        and record.train_no == state.payment_failure_train_no
    ):
        return ActionResult(True, "Payment failed due to gateway timeout. Retry or pick alternative.")

    key = f"{record.train_no}:{record.class_code}"
    matrix = state.seat_matrix.get(key)
    if not matrix:
        return ActionResult(False, "Fare lookup failed for payment", penalty=-0.05)

    total_fare = SeatMatrixManager.get_fare(matrix, record.quota, _tatkal_open(state)) * len(record.passengers)
    if total_fare > state.budget_remaining:
        _add_violation(state, "payment exceeds budget")
        return ActionResult(False, "Insufficient budget for payment", penalty=-0.10)

    state.budget_remaining -= total_fare
    state.total_fare_spent += total_fare
    record.fare_paid = total_fare

    return ActionResult(True, f"Payment successful for {pnr}; paid {total_fare:.2f}")


def handle_check_pnr(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    pnr = params.get("pnr") or state.pnr
    if not pnr:
        return ActionResult(False, "No PNR provided", penalty=-0.05)

    record = state.pnr_registry.get(pnr)
    if not record:
        return ActionResult(False, f"PNR {pnr} not found", penalty=-0.05)

    status_text = record.booking_status.value
    if record.waitlist_position:
        status_text += f"{record.waitlist_position}"

    return ActionResult(
        True,
        f"PNR {pnr}: {status_text}",
        data={"pnr_record": record.model_dump()},
    )


def handle_modify_journey(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    if state.time_step > 16:
        _add_violation(state, "modify_journey after chart preparation")
        return ActionResult(False, "Chart prepared; modifications are blocked", penalty=-0.10)

    pnr = params.get("pnr") or state.pnr
    if not pnr or pnr not in state.pnr_registry:
        return ActionResult(False, "PNR not found for modification", penalty=-0.05)

    mod_type = (params.get("modification_type") or "").strip()
    if mod_type == "change_class":
        new_class = (params.get("new_class_code") or "").strip()
        if not new_class:
            return ActionResult(False, "new_class_code is required", penalty=-0.05)
        state.selected_class = new_class
        state.pnr_registry[pnr].class_code = new_class
        return ActionResult(True, f"Journey modified to class {new_class}")

    if mod_type == "add_passenger":
        return handle_add_passenger(state, params)

    return ActionResult(True, f"Modification '{mod_type or 'none'}' acknowledged")


def handle_cancel(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    pnr = params.get("pnr") or state.pnr
    if not pnr:
        return ActionResult(False, "No PNR provided", penalty=-0.05)

    record = state.pnr_registry.get(pnr)
    if not record:
        return ActionResult(False, f"PNR {pnr} not found", penalty=-0.05)

    key = f"{record.train_no}:{record.class_code}"
    matrix = state.seat_matrix.get(key)
    if matrix:
        was_confirmed = record.booking_status == BookingStatusEnum.CNF
        for passenger_id in record.passengers:
            SeatMatrixManager.cancel_booking(matrix, record.quota, passenger_id, was_confirmed)

    if record.fare_paid > 0:
        state.budget_remaining += record.fare_paid
        state.total_fare_spent = max(0.0, state.total_fare_spent - record.fare_paid)

    penalty = -0.10 if record.booking_status == BookingStatusEnum.CNF else 0.0

    del state.pnr_registry[pnr]
    if state.pnr == pnr:
        state.pnr = None
        state.booking_status = None
        state.waitlist_position = None

    return ActionResult(True, f"Cancelled booking {pnr}", penalty=penalty)


def _validate_group_indices(state: IrctcBookingState, groups: List[Dict[str, Any]]) -> bool:
    all_indices: List[int] = []
    for group in groups:
        all_indices.extend(group.get("passenger_indices", []))
    expected = list(range(len(state.passengers)))
    return sorted(all_indices) == expected


def handle_split_booking(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    if not state.selected_train or not state.selected_class:
        _add_violation(state, "split booking without train selection")
        return ActionResult(False, "Select train/class before split_booking", penalty=-0.10)

    groups = params.get("groups") or params.get("splits") or []
    if not groups:
        return ActionResult(False, "groups are required", penalty=-0.05)

    if not _validate_group_indices(state, groups):
        _add_violation(state, "invalid split group coverage")
        return ActionResult(False, "groups must cover each passenger index exactly once", penalty=-0.05)

    tatkal_open = _tatkal_open(state)
    projected_cost = 0.0
    group_costs: List[float] = []

    for group in groups:
        quota = QuotaEnum(group.get("quota", QuotaEnum.General.value))
        class_code = group.get("class_code", state.selected_class)
        key = f"{state.selected_train}:{class_code}"
        matrix = state.seat_matrix.get(key)
        if not matrix:
            return ActionResult(False, f"No seat matrix for class {class_code}", penalty=-0.05)

        indices = group.get("passenger_indices", [])
        passengers = [state.passengers[idx] for idx in indices]
        if quota == QuotaEnum.Ladies and any(p.gender != GenderEnum.Female for p in passengers):
            _add_violation(state, "ladies split includes male passenger")
            return ActionResult(False, "Ladies split contains non-female passenger", penalty=-0.15)

        fare = SeatMatrixManager.get_fare(matrix, quota, tatkal_open) * len(indices)
        group_costs.append(fare)
        projected_cost += fare

    if projected_cost > state.budget_remaining:
        _add_violation(state, "split booking exceeds budget")
        return ActionResult(False, "Split booking exceeds remaining budget", penalty=-0.10)

    created_pnrs: List[str] = []
    for group, fare in zip(groups, group_costs):
        quota = QuotaEnum(group.get("quota", QuotaEnum.General.value))
        class_code = group.get("class_code", state.selected_class)
        key = f"{state.selected_train}:{class_code}"
        matrix = state.seat_matrix[key]

        statuses: List[BookingStatusEnum] = []
        wl_positions: List[int] = []
        passenger_ids = [f"P{idx + 1}" for idx in group.get("passenger_indices", [])]

        for passenger_id in passenger_ids:
            status, wl_pos = SeatMatrixManager.allocate_seat(matrix, quota, passenger_id)
            statuses.append(status)
            if wl_pos is not None:
                wl_positions.append(wl_pos)

        booking_status = BookingStatusEnum.CNF if all(s == BookingStatusEnum.CNF for s in statuses) else BookingStatusEnum.WL
        waitlist_position = max(wl_positions) if wl_positions else None
        pnr = _generate_pnr(state)
        state.pnr_registry[pnr] = PNRRecord(
            pnr=pnr,
            train_no=state.selected_train,
            class_code=class_code,
            quota=quota,
            passengers=passenger_ids,
            booking_status=booking_status,
            waitlist_position=waitlist_position,
            fare_paid=0.0,
        )
        created_pnrs.append(pnr)

    if created_pnrs:
        state.pnr = created_pnrs[-1]
        state.booking_status = state.pnr_registry[state.pnr].booking_status
        state.waitlist_position = state.pnr_registry[state.pnr].waitlist_position

    return ActionResult(
        True,
        f"Split booking created {len(created_pnrs)} PNR(s)",
        data={"pnrs": created_pnrs, "projected_cost": projected_cost},
    )


def _time_to_minutes(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def _minutes_between(start: str, end: str) -> int:
    start_m = _time_to_minutes(start)
    end_m = _time_to_minutes(end)
    diff = end_m - start_m
    if diff < 0:
        diff += 24 * 60
    return diff


def _best_direct_duration(state: IrctcBookingState, source: str, destination: str) -> int | None:
    durations = [
        train.duration_minutes
        for train in state.train_catalog.values()
        if train.source.lower() == source.lower() and train.destination.lower() == destination.lower()
    ]
    return min(durations) if durations else None


def _segment_has_capacity(state: IrctcBookingState, train_no: str, class_code: str, pax_count: int) -> int:
    key = f"{train_no}:{class_code}"
    matrix = state.seat_matrix.get(key)
    if not matrix:
        return 0
    slot = matrix.quota_allocations.get(QuotaEnum.General)
    if not slot:
        return 0
    return slot.confirmed_seats - pax_count


def _segment_total_fare(state: IrctcBookingState, train_no: str, class_code: str, pax_count: int) -> float:
    key = f"{train_no}:{class_code}"
    matrix = state.seat_matrix.get(key)
    if not matrix:
        return 10e9
    return SeatMatrixManager.get_fare(matrix, QuotaEnum.General, _tatkal_open(state)) * pax_count


def handle_choose_alternative(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    source = (params.get("source") or state.route_source or "").strip()
    destination = (params.get("destination") or state.route_destination or "").strip()
    multi_hop = bool(params.get("multi_hop", False))
    max_multiplier = float(params.get("max_duration_multiplier", 1.5))

    if not source or not destination:
        return ActionResult(False, "source and destination are required", penalty=-0.05)

    if not multi_hop:
        alternatives = [
            t.model_dump()
            for t in _availability_train_list(state, source, destination)
            if t.train_no != state.selected_train
        ]
        return ActionResult(True, f"Found {len(alternatives)} direct alternative(s)", data={"alternatives": alternatives})

    fastest_direct = _best_direct_duration(state, source, destination)
    if fastest_direct is None:
        return ActionResult(False, "No direct baseline route found for duration constraint", penalty=-0.05)

    max_duration = fastest_direct * max_multiplier
    pax_count = len(state.passengers)
    options: List[Dict[str, Any]] = []

    first_leg_trains = [
        t for t in state.train_catalog.values() if t.source.lower() == source.lower() and t.destination.lower() != destination.lower()
    ]

    second_leg_trains = [
        t for t in state.train_catalog.values() if t.destination.lower() == destination.lower() and t.source.lower() != source.lower()
    ]

    for first in first_leg_trains:
        for second in second_leg_trains:
            if first.destination.lower() != second.source.lower():
                continue

            transfer_minutes = _minutes_between(first.arrival_time, second.departure_time)
            if transfer_minutes < 60:
                continue

            total_duration = first.duration_minutes + transfer_minutes + second.duration_minutes
            if total_duration > max_duration:
                continue

            # Use SL when available, otherwise first class listed.
            first_class = "SL" if "SL" in first.available_classes else first.available_classes[0]
            second_class = "SL" if "SL" in second.available_classes else second.available_classes[0]

            fare_total = _segment_total_fare(state, first.train_no, first_class, pax_count) + _segment_total_fare(
                state, second.train_no, second_class, pax_count
            )
            if fare_total > state.budget_remaining:
                continue

            cap_a = _segment_has_capacity(state, first.train_no, first_class, pax_count)
            cap_b = _segment_has_capacity(state, second.train_no, second_class, pax_count)
            confirmation_score = min(cap_a, cap_b)

            options.append(
                {
                    "legs": [
                        {"train_no": first.train_no, "class_code": first_class},
                        {"train_no": second.train_no, "class_code": second_class},
                    ],
                    "transfer_minutes": transfer_minutes,
                    "total_duration_minutes": total_duration,
                    "total_fare": fare_total,
                    "confirmation_score": confirmation_score,
                }
            )

    if not options:
        return ActionResult(
            True,
            "No feasible multi-hop journey found under transfer, duration, and budget constraints",
            data={"multi_hop_options": []},
        )

    options.sort(key=lambda x: (-x["confirmation_score"], x["total_fare"], x["total_duration_minutes"]))
    best = options[0]
    return ActionResult(
        True,
        "Selected best multi-hop alternative",
        data={"best_option": best, "multi_hop_options": options[:5]},
    )


def handle_wait_step(state: IrctcBookingState, params: Dict[str, Any]) -> ActionResult:
    del params
    return ActionResult(True, "Waited one step for market changes")


ACTION_HANDLERS: Dict[ActionTypeEnum, Callable[[IrctcBookingState, Dict[str, Any]], ActionResult]] = {
    ActionTypeEnum.search_trains: handle_search_trains,
    ActionTypeEnum.check_availability: handle_check_availability,
    ActionTypeEnum.select_train: handle_select_train,
    ActionTypeEnum.add_passenger: handle_add_passenger,
    ActionTypeEnum.apply_quota: handle_apply_quota,
    ActionTypeEnum.book_ticket: handle_book_ticket,
    ActionTypeEnum.pay: handle_pay,
    ActionTypeEnum.check_pnr: handle_check_pnr,
    ActionTypeEnum.modify_journey: handle_modify_journey,
    ActionTypeEnum.cancel: handle_cancel,
    ActionTypeEnum.split_booking: handle_split_booking,
    ActionTypeEnum.choose_alternative: handle_choose_alternative,
    ActionTypeEnum.wait_step: handle_wait_step,
}
