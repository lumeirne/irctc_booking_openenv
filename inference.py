"""Groq inference script for IRCTC OpenEnv tasks.

This script emits strict evaluator logs:
[START] task=<task_name> env=<benchmark> model=<model_name>
[STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
[END]   success=<true|false> steps=<n> rewards=<r1,r2,...,rn>
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI

from irctc_booking.client import IrctcBookingEnv
from irctc_booking.models import ActionTypeEnum, IrctcBookingAction, IrctcBookingObservation

from dotenv import load_dotenv
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN")
BENCHMARK = os.getenv("BENCHMARK", "irctc_booking")
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860")
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")
MAX_STEPS = min(int(os.getenv("MAX_STEPS", "20")), 20)
TEMPERATURE = 0.0
TASK_IDS = [int(x.strip()) for x in os.getenv("TASK_IDS", "0,1,2").split(",") if x.strip()]


TASK_CONTEXT: Dict[int, Dict[str, Any]] = {
    0: {
        "name": "simple_confirmed_booking",
        "source": "New Delhi",
        "destination": "Mumbai Central",
    },
    1: {
        "name": "waitlist_management",
        "source": "New Delhi",
        "destination": "Chennai Central",
    },
    2: {
        "name": "tatkal_rush_mixed_quotas",
        "source": "New Delhi",
        "destination": "Lucknow",
    },
}


@dataclass
class EpisodeRun:
    rewards: List[float]
    steps: int
    success: bool


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} rewards={rewards_str}",
        flush=True,
    )


def normalize_reward(raw_reward: Any) -> float:
    """Keep emitted rewards strictly inside (0, 1)."""
    try:
        value = float(raw_reward)
    except (TypeError, ValueError):
        value = 0.01
    return max(0.01, min(0.99, value))


def format_action(action_type: str, params: Dict[str, Any]) -> str:
    if not params:
        return f"{action_type}()"
    kv = ", ".join(f"{k}={json.dumps(v)}" for k, v in params.items())
    return f"{action_type}({kv})"


def safe_action_type(action_type: str) -> str:
    if action_type in {a.value for a in ActionTypeEnum}:
        return action_type
    return ActionTypeEnum.search_trains.value


def deterministic_fallback(
    step: int,
    observation: IrctcBookingObservation,
    task_context: Dict[str, Any],
) -> Dict[str, Any]:
    if step == 1:
        return {
            "action_type": ActionTypeEnum.search_trains.value,
            "params": {
                "source": task_context["source"],
                "destination": task_context["destination"],
                "date": "2026-04-04",
            },
        }

    if step == 2 and observation.trains:
        best = max(observation.trains, key=lambda t: t.approximate_count)
        return {
            "action_type": ActionTypeEnum.select_train.value,
            "params": {"train_no": best.train_no, "class_code": best.class_code},
        }

    if step == 3:
        return {
            "action_type": ActionTypeEnum.apply_quota.value,
            "params": {"quota": "General"},
        }

    if not observation.pnr:
        return {"action_type": ActionTypeEnum.book_ticket.value, "params": {}}

    if observation.booking_status and observation.booking_status.value == "WL":
        return {"action_type": ActionTypeEnum.wait_step.value, "params": {}}

    return {"action_type": ActionTypeEnum.pay.value, "params": {"pnr": observation.pnr}}


def parse_model_action(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return None

    if "```" in text:
        text = text.replace("```json", "").replace("```", "").strip()

    try:
        obj = json.loads(text)
        if not isinstance(obj, dict):
            return None
        return {
            "action_type": safe_action_type(str(obj.get("action_type", "search_trains"))),
            "params": obj.get("params", {}) if isinstance(obj.get("params", {}), dict) else {},
        }
    except json.JSONDecodeError:
        return None


def build_prompt(
    task_context: Dict[str, Any],
    observation: IrctcBookingObservation,
    step: int,
) -> str:
    obs_payload = {
        "task_id": observation.task_id,
        "message": observation.message,
        "pnr": observation.pnr,
        "booking_status": observation.booking_status.value if observation.booking_status else None,
        "waitlist_position": observation.waitlist_position,
        "steps_remaining": observation.steps_remaining,
        "tatkal_status": observation.tatkal_status.value if observation.tatkal_status else None,
        "tatkal_countdown": observation.tatkal_countdown,
        "chart_prepared": observation.chart_prepared,
        "trains": [
            {
                "train_no": t.train_no,
                "class_code": t.class_code,
                "availability_label": t.availability_label.value,
                "approximate_count": t.approximate_count,
            }
            for t in observation.trains
        ][:8],
    }

    return (
        "You are an IRCTC booking agent. Reply with strict JSON only. "
        "Schema: {\"action_type\": <valid_action>, \"params\": {...}}. "
        "Valid actions: search_trains, check_availability, select_train, add_passenger, apply_quota, "
        "book_ticket, pay, check_pnr, modify_journey, cancel, split_booking, choose_alternative, wait_step. "
        "Do not include markdown.\n"
        f"Task: {task_context['name']} (source={task_context['source']}, destination={task_context['destination']}).\n"
        f"Step: {step}.\n"
        f"Observation: {json.dumps(obs_payload, ensure_ascii=True)}"
    )


async def choose_action_with_model(
    client: OpenAI,
    task_context: Dict[str, Any],
    observation: IrctcBookingObservation,
    step: int,
) -> Dict[str, Any]:
    prompt = build_prompt(task_context, observation, step)
    # Keep the event loop free so local websocket heartbeats are not starved
    # while waiting on slow external provider responses.
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "Return only valid JSON action payload."},
            {"role": "user", "content": prompt},
        ],
        temperature=TEMPERATURE,
        max_tokens=180,
        stream=False,
    )

    raw = (response.choices[0].message.content or "").strip()
    parsed = parse_model_action(raw)
    if parsed is not None:
        return parsed
    return deterministic_fallback(step, observation, task_context)


async def run_episode(
    env: IrctcBookingEnv,
    llm_client: OpenAI,
    task_id: int,
    seed: int,
) -> EpisodeRun:
    task_context = TASK_CONTEXT.get(task_id, {"name": f"task_{task_id}", "source": "", "destination": ""})
    log_start(task_context["name"], BENCHMARK, MODEL_NAME)

    rewards: List[float] = []
    steps_taken = 0
    success = False

    observation: Optional[IrctcBookingObservation] = None

    try:
        reset_result = await env.reset(task_id=task_id, seed=seed)
        observation = reset_result.observation

        for step in range(1, MAX_STEPS + 1):
            action_payload = await choose_action_with_model(llm_client, task_context, observation, step)
            action_type = safe_action_type(str(action_payload.get("action_type", "search_trains")))
            params = action_payload.get("params", {})
            if not isinstance(params, dict):
                params = {}

            action = IrctcBookingAction(action_type=ActionTypeEnum(action_type), params=params)
            step_result = await env.step(action)

            observation = step_result.observation
            reward = normalize_reward(step_result.reward)
            done = bool(step_result.done)
            err = None
            if isinstance(observation.metadata, dict):
                err = observation.metadata.get("error")

            rewards.append(reward)
            steps_taken = step
            log_step(step, format_action(action_type, params), reward, done, err)

            if done:
                break

        if observation and isinstance(observation.metadata, dict):
            meta_success = observation.metadata.get("success")
            if isinstance(meta_success, bool):
                success = meta_success
            else:
                success = bool(rewards and sum(rewards) > 0)
        else:
            success = bool(rewards and sum(rewards) > 0)

    except Exception as exc:
        # Keep evaluator output deterministic and structured.
        fallback_reward = 0.01
        rewards.append(fallback_reward)
        log_step(
            steps_taken + 1,
            "internal_error()",
            fallback_reward,
            True,
            str(exc),
        )
        success = False
    finally:
        log_end(success, steps_taken, rewards)

    return EpisodeRun(rewards=rewards, steps=steps_taken, success=success)


async def main() -> None:
    if HF_TOKEN is None:
        raise ValueError("HF_TOKEN environment variable is required")

    llm_client = OpenAI(
        base_url=API_BASE_URL,
        api_key=HF_TOKEN,
    )

    if LOCAL_IMAGE_NAME:
        env = await IrctcBookingEnv.from_docker_image(LOCAL_IMAGE_NAME)
    else:
        env = IrctcBookingEnv(base_url=ENV_BASE_URL)
        await env.connect()

    try:
        for offset, task_id in enumerate(TASK_IDS):
            await run_episode(env=env, llm_client=llm_client, task_id=task_id, seed=42 + offset)
    finally:
        await env.close()


if __name__ == "__main__":
    asyncio.run(main())
