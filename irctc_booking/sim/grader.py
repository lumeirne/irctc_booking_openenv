"""Deterministic trajectory grader for completed episodes."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from irctc_booking.models import BookingStatusEnum, GroundTruth, IrctcBookingState


class EpisodeGrader:
    """Scores episodes in [0.0, 1.0] with deterministic weighted components."""

    def __init__(self, ground_truth_db: Dict[int, GroundTruth]) -> None:
        self.ground_truth_db = ground_truth_db

    def score(
        self,
        *,
        trajectory: List[Dict[str, Any]],
        final_state: IrctcBookingState,
    ) -> Tuple[float, Dict[str, float]]:
        if self._detect_state_access(trajectory):
            return 0.01, {
                "final_booking_success": 0.01,
                "optimality_score": 0.01,
                "efficiency_score": 0.01,
                "rule_compliance": 0.01,
            }

        success = self._clamp(self._final_booking_success(final_state))
        optimality = self._clamp(self._optimality_score(final_state))
        efficiency = self._clamp(self._efficiency_score(final_state))
        compliance = self._clamp(self._rule_compliance(final_state))

        score = (
            0.40 * success
            + 0.20 * optimality
            + 0.20 * efficiency
            + 0.20 * compliance
        )
        score = self._clamp(score)

        return score, {
            "final_booking_success": success,
            "optimality_score": optimality,
            "efficiency_score": efficiency,
            "rule_compliance": compliance,
        }

    @staticmethod
    def _clamp(value: float, low: float = 0.01, high: float = 0.99) -> float:
        """Clamp a score to strictly within (0, 1)."""
        return max(low, min(high, value))

    def _detect_state_access(self, trajectory: List[Dict[str, Any]]) -> bool:
        for step in trajectory:
            info = step.get("info", {})
            if info.get("state_called"):
                return True
            action = step.get("action", {})
            if action.get("action_type") == "state":
                return True
        return False

    def _final_booking_success(self, state: IrctcBookingState) -> float:
        if not state.passengers:
            return self._clamp(0.0)

        total = len(state.passengers)
        cnf = 0
        for record in state.pnr_registry.values():
            if record.booking_status == BookingStatusEnum.CNF:
                cnf += len(record.passengers)

        if cnf == total:
            return self._clamp(1.0)
        if cnf >= total / 2:
            return self._clamp(0.5)
        return self._clamp(0.0)

    def _optimality_score(self, state: IrctcBookingState) -> float:
        gt = self.ground_truth_db.get(state.task_id or -1)
        if gt is None or gt.minimum_fare_inr <= 0:
            return self._clamp(0.5)

        ratio = state.total_fare_spent / gt.minimum_fare_inr if gt.minimum_fare_inr > 0 else 9.0
        if ratio <= 1.10:
            return self._clamp(1.0)
        if ratio <= 1.50:
            return self._clamp(1.0 - ((ratio - 1.10) / 0.40))
        return self._clamp(0.0)

    def _efficiency_score(self, state: IrctcBookingState) -> float:
        return self._clamp(1.0 - (state.step_count / 20.0))

    def _rule_compliance(self, state: IrctcBookingState) -> float:
        unique_violations = len(set(state.rule_violations))
        return self._clamp(1.0 - (0.1 * unique_violations))
