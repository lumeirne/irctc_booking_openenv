---
title: IRCTC Booking Environment
emoji: 🚆
colorFrom: green
colorTo: blue
sdk: docker
pinned: false
app_port: 7860
base_path: /web
tags:
  - openenv
---

# IRCTC Booking OpenEnv Environment

Real-world OpenEnv environment that simulates Indian Railways (IRCTC) ticket booking under realistic constraints:
- quota eligibility (General, Tatkal, Ladies, Senior Citizen)
- partial observability (coarse search vs exact availability)
- waitlist dynamics and cancellation-based promotions
- budget constraints and payment failures
- high-demand seat contention and decoy-train collapse

The environment supports standard OpenEnv interactions via reset/step/state.

## Why This Environment

This environment models a real operational workflow users perform daily: railway ticket planning and booking under uncertainty.
Agents are evaluated on success, cost, rule compliance, and decision efficiency across increasingly hard tasks.

## Tasks (Easy to Hard)

1. Task 0: Simple Confirmed Booking (easy)
- Single passenger.
- Multiple trains with confirmed seats.
- Budget INR 2,000.

2. Task 1: Waitlist Management (medium)
- Two passengers.
- Waitlist pressure and cancellation-driven promotions.
- Budget INR 5,000.

3. Task 2: Tatkal Rush With Mixed Quotas (hard)
- Four passengers under quota/time pressure.
- Deterministic payment failure event.
- Decoy train loses most seats mid-episode.
- Budget INR 12,000.

## Action Space

The action schema is typed via Pydantic and supports:
- search_trains
- check_availability
- select_train
- add_passenger
- apply_quota
- book_ticket
- pay
- check_pnr
- modify_journey
- cancel
- split_booking
- choose_alternative
- wait_step

## Observation Space

Each observation includes:
- train summaries (availability label + approximate seats)
- active PNR and booking status
- waitlist position
- tatkal status and countdown
- chart preparation flag
- step reward and steps remaining

Full exact seat matrix details are exposed only after check_availability.

## Reward Design

Per-step reward uses shaped components:
- 0.30 booking_progress
- 0.25 confirmation_probability_score
- 0.20 rule_compliance
- 0.15 cost_efficiency
- 0.10 step_efficiency

Additional bonuses and penalties:
- +0.05 waitlist promotion via wait_step
- -0.10 unnecessary CNF cancellation
- -0.15 invalid quota eligibility
- -0.05 duplicate consecutive action
- -0.10 booking WL when better CNF option exists in budget

## Grading

Final episode score is deterministic in [0.0, 1.0]:
- 0.40 final_booking_success
- 0.20 optimality_score
- 0.20 efficiency_score
- 0.20 rule_compliance

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run server locally

```bash
uvicorn irctc_booking.server.app:app --host 0.0.0.0 --port 7860
```

### 3. Test OpenEnv endpoints

```bash
curl -X POST http://localhost:7860/reset -H "Content-Type: application/json" -d '{"task_id":0,"seed":42}'
curl -X GET "http://localhost:7860/state"
```

### 4. Validate OpenEnv compliance

```bash
openenv validate
```

## Baseline Inference Scripts

Both root-level inference scripts:
- use OpenAI client
- run tasks configured by TASK_IDS (default 0,1,2)
- emit strict structured logs:

```text
[START] task=<task_name> env=<benchmark> model=<model_name>
[STEP] step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
[END] success=<true|false> steps=<n> rewards=<r1,r2,...,rn>
```

### 1) Hugging Face router script: inference_hf.py

Required environment variables:
- HF_TOKEN

Optional:
- API_BASE_URL (default: https://router.huggingface.co/v1)
- MODEL_NAME (default: Qwen/Qwen2.5-72B-Instruct)
- ENV_BASE_URL (default: http://localhost:7860)
- LOCAL_IMAGE_NAME (if using from_docker_image)
- TASK_IDS (default: 0,1,2)

Run:

```bash
python inference_hf.py
```

### 2) Groq script: inference.py

Required environment variables:
- GROQ_API_KEY

Optional:
- API_BASE_URL (default: https://api.groq.com/openai/v1)
- MODEL_NAME (default: qwen/qwen3-32b)
- ENV_BASE_URL (default: http://localhost:7860)
- LOCAL_IMAGE_NAME (if using from_docker_image)
- TASK_IDS (default: 0,1,2)

Run:

```bash
python inference.py
```

## Docker

Build:

```bash
docker build -t irctc-booking-env .
```

Run:

```bash
docker run --rm -p 7860:7860 irctc-booking-env
```

Health:

```bash
curl http://localhost:7860/health
```

## Deployment to Hugging Face Spaces

```bash
openenv push
```

After deployment, ensure the space responds on:
- POST /reset
- POST /step
- GET /state
- GET /health

## Notes on Reproducibility

- Task transitions are deterministic for same task_id + seed.
- Baseline inference uses temperature 0.0.
- Event scheduling is seeded and repeatable.
