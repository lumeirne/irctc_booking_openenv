"""Task definitions and deterministic scenario data for the IRCTC simulator."""

from __future__ import annotations

from typing import Any, Dict, List

from irctc_booking.models import (
    ConcessionEnum,
    GenderEnum,
    GroundTruth,
    Passenger,
    QuotaEnum,
    TaskDescriptor,
    TrainInfo,
)

TRAIN_DATABASE: Dict[str, TrainInfo] = {
    "12301": TrainInfo(
        train_no="12301",
        train_name="Rajdhani Express",
        source="New Delhi",
        destination="Mumbai Central",
        departure_time="16:55",
        arrival_time="08:35",
        duration_minutes=940,
        available_classes=["3A", "2A", "1A"],
    ),
    "12951": TrainInfo(
        train_no="12951",
        train_name="Mumbai Rajdhani",
        source="New Delhi",
        destination="Mumbai Central",
        departure_time="17:00",
        arrival_time="08:40",
        duration_minutes=940,
        available_classes=["3A", "2A", "SL"],
    ),
    "12909": TrainInfo(
        train_no="12909",
        train_name="Garib Rath Express",
        source="New Delhi",
        destination="Mumbai Central",
        departure_time="15:30",
        arrival_time="07:15",
        duration_minutes=945,
        available_classes=["3A", "SL"],
    ),
    "12621": TrainInfo(
        train_no="12621",
        train_name="Tamil Nadu Express",
        source="New Delhi",
        destination="Chennai Central",
        departure_time="22:30",
        arrival_time="07:05",
        duration_minutes=515,
        available_classes=["3A", "2A", "SL"],
    ),
    "12615": TrainInfo(
        train_no="12615",
        train_name="Grand Trunk Express",
        source="New Delhi",
        destination="Chennai Central",
        departure_time="19:15",
        arrival_time="05:50",
        duration_minutes=635,
        available_classes=["3A", "SL"],
    ),
    "12430": TrainInfo(
        train_no="12430",
        train_name="Lucknow AC SF",
        source="New Delhi",
        destination="Lucknow",
        departure_time="22:20",
        arrival_time="06:00",
        duration_minutes=460,
        available_classes=["3A", "2A", "SL"],
    ),
    "12229": TrainInfo(
        train_no="12229",
        train_name="Lucknow Mail",
        source="New Delhi",
        destination="Lucknow",
        departure_time="23:00",
        arrival_time="08:30",
        duration_minutes=570,
        available_classes=["3A", "SL"],
    ),
    "12553": TrainInfo(
        train_no="12553",
        train_name="Vaishali SF Express",
        source="New Delhi",
        destination="Lucknow",
        departure_time="20:30",
        arrival_time="05:45",
        duration_minutes=555,
        available_classes=["3A", "2A", "SL"],
    ),
    # Extra trains to allow multi-hop search in choose_alternative.
    "14010": TrainInfo(
        train_no="14010",
        train_name="Kanpur Intercity",
        source="New Delhi",
        destination="Kanpur Central",
        departure_time="06:00",
        arrival_time="11:30",
        duration_minutes=330,
        available_classes=["SL", "3A"],
    ),
    "15018": TrainInfo(
        train_no="15018",
        train_name="Kanpur Lucknow Express",
        source="Kanpur Central",
        destination="Lucknow",
        departure_time="12:45",
        arrival_time="14:05",
        duration_minutes=80,
        available_classes=["SL"],
    ),
}


TASK_DESCRIPTORS: List[TaskDescriptor] = [
    TaskDescriptor(
        task_id=0,
        name="Simple Confirmed Booking",
        description="Book one confirmed ticket for a single passenger within budget.",
        difficulty="easy",
    ),
    TaskDescriptor(
        task_id=1,
        name="Waitlist Management",
        description="Handle waitlist and timed journey modifications under constraints.",
        difficulty="medium",
    ),
    TaskDescriptor(
        task_id=2,
        name="Tatkal Rush With Mixed Quotas",
        description="Handle payment failure, decoy train contention, and quota strategy.",
        difficulty="hard",
    ),
]


GROUND_TRUTHS: Dict[int, GroundTruth] = {
    0: GroundTruth(
        task_id=0,
        optimal_train_no="12909",
        optimal_class_code="SL",
        optimal_quota=QuotaEnum.General,
        minimum_fare_inr=700.0,
        best_confirmation_strategy="Direct CNF booking in General quota on lowest-fare train",
    ),
    1: GroundTruth(
        task_id=1,
        optimal_train_no="12615",
        optimal_class_code="SL",
        optimal_quota=QuotaEnum.General,
        minimum_fare_inr=2000.0,
        best_confirmation_strategy="Book affordable SL seats and avoid late modifications",
    ),
    2: GroundTruth(
        task_id=2,
        optimal_train_no="12229",
        optimal_class_code="SL",
        optimal_quota=QuotaEnum.General,
        minimum_fare_inr=3400.0,
        best_confirmation_strategy="Avoid decoy deterioration and recover from payment failure",
    ),
}


def create_task_0_config() -> Dict[str, Any]:
    return {
        "task_id": 0,
        "name": "Simple Confirmed Booking",
        "difficulty": "easy",
        "source": "New Delhi",
        "destination": "Mumbai Central",
        "passengers": [
            Passenger(name="Rajesh Kumar", age=35, gender=GenderEnum.Male),
        ],
        "budget_total": 2000.0,
        "trains": ["12301", "12951", "12909"],
        "seat_configs": {
            "12301": {
                "3A": {
                    QuotaEnum.General: {"total_seats": 25, "fare_base_inr": 1500.0},
                    QuotaEnum.Tatkal: {"total_seats": 5, "fare_base_inr": 1500.0},
                }
            },
            "12951": {
                "3A": {
                    QuotaEnum.General: {"total_seats": 30, "fare_base_inr": 1450.0},
                    QuotaEnum.Tatkal: {"total_seats": 5, "fare_base_inr": 1450.0},
                },
                "SL": {
                    QuotaEnum.General: {"total_seats": 50, "fare_base_inr": 800.0},
                    QuotaEnum.Tatkal: {"total_seats": 10, "fare_base_inr": 800.0},
                },
            },
            "12909": {
                "SL": {
                    QuotaEnum.General: {"total_seats": 45, "fare_base_inr": 700.0},
                    QuotaEnum.Tatkal: {"total_seats": 10, "fare_base_inr": 700.0},
                }
            },
        },
        "cancellation_events": [],
        "contention_events": [],
    }


def create_task_1_config() -> Dict[str, Any]:
    return {
        "task_id": 1,
        "name": "Waitlist Management",
        "difficulty": "medium",
        "source": "New Delhi",
        "destination": "Chennai Central",
        "passengers": [
            Passenger(name="Priya Sharma", age=28, gender=GenderEnum.Female),
            Passenger(name="Amit Patel", age=32, gender=GenderEnum.Male),
        ],
        "budget_total": 5000.0,
        "trains": ["12621", "12615"],
        "seat_configs": {
            "12621": {
                "3A": {
                    QuotaEnum.General: {"total_seats": 1, "fare_base_inr": 2100.0},
                    QuotaEnum.Tatkal: {"total_seats": 2, "fare_base_inr": 2100.0},
                    QuotaEnum.Ladies: {"total_seats": 1, "fare_base_inr": 2100.0},
                },
                "SL": {
                    QuotaEnum.General: {"total_seats": 12, "fare_base_inr": 1100.0},
                    QuotaEnum.Tatkal: {"total_seats": 4, "fare_base_inr": 1100.0},
                },
            },
            "12615": {
                "SL": {
                    QuotaEnum.General: {"total_seats": 20, "fare_base_inr": 1000.0},
                    QuotaEnum.Tatkal: {"total_seats": 5, "fare_base_inr": 1000.0},
                }
            },
        },
        "cancellation_events": [
            {
                "time_step": 7,
                "train_no": "12621",
                "class_code": "3A",
                "quota": QuotaEnum.General,
                "passenger_id": None,
            },
            {
                "time_step": 10,
                "train_no": "12621",
                "class_code": "3A",
                "quota": QuotaEnum.General,
                "passenger_id": None,
            },
        ],
        "contention_events": [
            {
                "time_step": 3,
                "train_no": "12621",
                "class_code": "3A",
                "quota": QuotaEnum.General,
                "seats_to_reduce": 1,
            }
        ],
    }


def create_task_2_config() -> Dict[str, Any]:
    return {
        "task_id": 2,
        "name": "Tatkal Rush With Mixed Quotas",
        "difficulty": "hard",
        "source": "New Delhi",
        "destination": "Lucknow",
        "passengers": [
            Passenger(name="Sunita Verma", age=45, gender=GenderEnum.Female),
            Passenger(name="Rakesh Verma", age=48, gender=GenderEnum.Male),
            Passenger(name="Anjali Verma", age=22, gender=GenderEnum.Female),
            Passenger(name="Vikram Verma", age=19, gender=GenderEnum.Male),
        ],
        "budget_total": 12000.0,
        "trains": ["12430", "12229", "12553", "14010", "15018"],
        "primary_train_no": "12430",
        "payment_failure_step": 3,
        "seat_configs": {
            "12430": {
                "3A": {
                    QuotaEnum.General: {"total_seats": 3, "fare_base_inr": 1800.0},
                    QuotaEnum.Tatkal: {"total_seats": 8, "fare_base_inr": 1800.0},
                    QuotaEnum.Ladies: {"total_seats": 2, "fare_base_inr": 1800.0},
                },
                "SL": {
                    QuotaEnum.General: {"total_seats": 10, "fare_base_inr": 900.0},
                    QuotaEnum.Tatkal: {"total_seats": 12, "fare_base_inr": 900.0},
                    QuotaEnum.Ladies: {"total_seats": 5, "fare_base_inr": 900.0},
                },
            },
            "12229": {
                "SL": {
                    QuotaEnum.General: {"total_seats": 25, "fare_base_inr": 850.0},
                    QuotaEnum.Tatkal: {"total_seats": 8, "fare_base_inr": 850.0},
                    QuotaEnum.Ladies: {"total_seats": 5, "fare_base_inr": 850.0},
                }
            },
            "12553": {
                "3A": {
                    QuotaEnum.General: {"total_seats": 25, "fare_base_inr": 1700.0},
                    QuotaEnum.Tatkal: {"total_seats": 5, "fare_base_inr": 1700.0},
                    QuotaEnum.Ladies: {"total_seats": 5, "fare_base_inr": 1700.0},
                },
                "SL": {
                    QuotaEnum.General: {"total_seats": 40, "fare_base_inr": 800.0},
                    QuotaEnum.Tatkal: {"total_seats": 10, "fare_base_inr": 800.0},
                    QuotaEnum.Ladies: {"total_seats": 8, "fare_base_inr": 800.0},
                },
            },
            "14010": {
                "SL": {
                    QuotaEnum.General: {"total_seats": 15, "fare_base_inr": 600.0}
                }
            },
            "15018": {
                "SL": {
                    QuotaEnum.General: {"total_seats": 15, "fare_base_inr": 250.0}
                }
            },
        },
        "cancellation_events": [
            {
                "time_step": 12,
                "train_no": "12430",
                "class_code": "3A",
                "quota": QuotaEnum.General,
                "passenger_id": None,
            }
        ],
        "contention_events": [
            {"time_step": 2, "train_no": "12430", "class_code": "3A", "quota": QuotaEnum.General, "seats_to_reduce": 1},
            {"time_step": 7, "train_no": "12430", "class_code": "3A", "quota": QuotaEnum.General, "seats_to_reduce": 1},
            {"time_step": 14, "train_no": "12430", "class_code": "SL", "quota": QuotaEnum.General, "seats_to_reduce": 3},
            {"time_step": 6, "train_no": "12553", "class_code": "3A", "quota": QuotaEnum.General, "seats_to_reduce": 6},
            {"time_step": 7, "train_no": "12553", "class_code": "3A", "quota": QuotaEnum.General, "seats_to_reduce": 6},
            {"time_step": 8, "train_no": "12553", "class_code": "3A", "quota": QuotaEnum.General, "seats_to_reduce": 5},
            {"time_step": 9, "train_no": "12553", "class_code": "3A", "quota": QuotaEnum.General, "seats_to_reduce": 4},
            {"time_step": 6, "train_no": "12553", "class_code": "SL", "quota": QuotaEnum.General, "seats_to_reduce": 10},
            {"time_step": 7, "train_no": "12553", "class_code": "SL", "quota": QuotaEnum.General, "seats_to_reduce": 10},
            {"time_step": 8, "train_no": "12553", "class_code": "SL", "quota": QuotaEnum.General, "seats_to_reduce": 8},
            {"time_step": 9, "train_no": "12553", "class_code": "SL", "quota": QuotaEnum.General, "seats_to_reduce": 8},
        ],
    }


def get_task_config(task_id: int) -> Dict[str, Any]:
    if task_id == 0:
        return create_task_0_config()
    if task_id == 1:
        return create_task_1_config()
    if task_id == 2:
        return create_task_2_config()
    raise ValueError(f"Invalid task_id: {task_id}")


def get_train_info(train_no: str) -> TrainInfo:
    if train_no not in TRAIN_DATABASE:
        raise ValueError(f"Unknown train number: {train_no}")
    return TRAIN_DATABASE[train_no]


def get_trains_for_route(source: str, destination: str) -> List[TrainInfo]:
    return [
        t
        for t in TRAIN_DATABASE.values()
        if t.source.lower() == source.lower() and t.destination.lower() == destination.lower()
    ]


def list_tasks() -> List[TaskDescriptor]:
    return TASK_DESCRIPTORS.copy()
