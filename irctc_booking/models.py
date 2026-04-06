"""Typed models for the IRCTC Booking OpenEnv environment."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from openenv.core.env_server.types import Action, Observation, State
from pydantic import BaseModel, Field


class GenderEnum(str, Enum):
    Male = "Male"
    Female = "Female"
    Other = "Other"


class ConcessionEnum(str, Enum):
    Senior_Citizen = "Senior_Citizen"
    none = "None"


class QuotaEnum(str, Enum):
    General = "General"
    Tatkal = "Tatkal"
    Ladies = "Ladies"
    Senior_Citizen = "Senior_Citizen"


class BookingStatusEnum(str, Enum):
    CNF = "CNF"
    WL = "WL"
    PQWL = "PQWL"
    RAC = "RAC"


class TatkalStatusEnum(str, Enum):
    open = "open"
    closed = "closed"
    not_yet_open = "not_yet_open"


class AvailabilityLabel(str, Enum):
    Available = "Available"
    Few_Seats = "Few Seats"
    WL = "WL"
    Fully_Booked = "Fully Booked"


class ActionTypeEnum(str, Enum):
    search_trains = "search_trains"
    check_availability = "check_availability"
    select_train = "select_train"
    add_passenger = "add_passenger"
    apply_quota = "apply_quota"
    book_ticket = "book_ticket"
    pay = "pay"
    check_pnr = "check_pnr"
    modify_journey = "modify_journey"
    cancel = "cancel"
    split_booking = "split_booking"
    choose_alternative = "choose_alternative"
    wait_step = "wait_step"


class Passenger(BaseModel):
    name: str
    age: int = Field(ge=1, le=120)
    gender: GenderEnum
    concession: Optional[ConcessionEnum] = None


class TrainInfo(BaseModel):
    train_no: str
    train_name: str
    source: str
    destination: str
    departure_time: str
    arrival_time: str
    duration_minutes: int
    available_classes: List[str]


class SeatAvailability(BaseModel):
    class_code: str
    quota: QuotaEnum
    confirmed_seats: int
    waitlist_count: int
    fare_inr: float


class TrainAvailabilitySummary(BaseModel):
    train_no: str
    train_name: str
    class_code: str
    availability_label: AvailabilityLabel
    approximate_count: int


class QuotaSlot(BaseModel):
    total_seats: int
    confirmed_seats: int
    waitlist: List[str]
    fare_base_inr: float
    tatkal_surcharge_pct: float = 0.30


class SeatMatrix(BaseModel):
    train_no: str
    class_code: str
    quota_allocations: Dict[QuotaEnum, QuotaSlot]


class PNRRecord(BaseModel):
    pnr: str
    train_no: str
    class_code: str
    quota: QuotaEnum
    passengers: List[str]
    booking_status: BookingStatusEnum
    waitlist_position: Optional[int] = None
    fare_paid: float = 0.0


class TaskDescriptor(BaseModel):
    task_id: int
    name: str
    description: str
    difficulty: Literal["easy", "medium", "hard"]


class GroundTruth(BaseModel):
    task_id: int
    optimal_train_no: str
    optimal_class_code: str
    optimal_quota: QuotaEnum
    minimum_fare_inr: float
    best_confirmation_strategy: str


class IrctcBookingAction(Action):
    action_type: ActionTypeEnum
    params: Dict[str, Any] = Field(default_factory=dict)


class IrctcBookingObservation(Observation):
    task_id: Optional[int] = None
    trains: List[TrainAvailabilitySummary] = Field(default_factory=list)
    pnr: Optional[str] = None
    message: str = ""
    step_reward: float = 0.0
    steps_remaining: int = 20
    tatkal_countdown: int = 10
    booking_status: Optional[BookingStatusEnum] = None
    waitlist_position: Optional[int] = None
    tatkal_status: Optional[TatkalStatusEnum] = None
    chart_prepared: bool = False


class IrctcBookingState(State):
    task_id: Optional[int] = None
    seed: Optional[int] = None
    time_step: int = 0
    passengers: List[Passenger] = Field(default_factory=list)
    selected_train: Optional[str] = None
    selected_class: Optional[str] = None
    applied_quota: Optional[QuotaEnum] = None
    pnr: Optional[str] = None
    booking_status: Optional[BookingStatusEnum] = None
    waitlist_position: Optional[int] = None
    seat_matrix: Dict[str, SeatMatrix] = Field(default_factory=dict)
    train_catalog: Dict[str, TrainInfo] = Field(default_factory=dict)
    budget_total: float = 0.0
    budget_remaining: float = 0.0
    cancellation_events_log: List[Dict[str, Any]] = Field(default_factory=list)
    last_action: Optional[IrctcBookingAction] = None
    done: bool = False
    rule_violations: List[str] = Field(default_factory=list)
    total_fare_spent: float = 0.0
    pnr_registry: Dict[str, PNRRecord] = Field(default_factory=dict)
    state_access_count: int = 0
    route_source: Optional[str] = None
    route_destination: Optional[str] = None
    payment_failure_step: Optional[int] = None
    payment_failure_train_no: Optional[str] = None
