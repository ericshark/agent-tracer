"""Seed demo data: a demo account, project, API key, and a realistic set of
traces from a fictional "travel concierge" agent — including failures worth
debugging.

Run:  python -m app.seed          (uses DATABASE_URL from the environment)
"""

import asyncio
import os
import random
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.experiments import JOB_KIND
from app.core.ingest import ingest_batch
from app.core.jobs import drain_jobs, enqueue
from app.core.scores import upsert_score
from app.core.security import generate_api_key, hash_password
from app.db import get_session_factory
from app.logging_config import configure_logging
from app.models import (
    ApiKey,
    Dataset,
    DatasetItem,
    Evaluator,
    Experiment,
    ExperimentItem,
    Project,
    Trace,
    User,
)
from app.schemas.ingest import SpanErrorIn, SpanIn, TraceIn
from app.schemas.scores import ScoreBase

DEMO_EMAIL = "demo@agenttracer.dev"
DEMO_NAME = "Demo User"
DEMO_DATASET = "trip-requests"

rng = random.Random(42)


def _hex(n: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


USER_QUESTIONS = [
    "I need a trip to Tokyo in October for 5 days, mid-range budget.",
    "Find me a beach holiday in Portugal for two adults next month.",
    "Plan a weekend in Rome — flights from Berlin and a hotel near the centre.",
    "What's the cheapest way to get to New York before the 15th?",
    "Book something relaxing in the Alps, spa hotel, 3 nights.",
    "Family trip to Barcelona in the school holidays, 4 people.",
]

SESSION_IDS = ["sess-aurora", "sess-basil", "sess-cedar", None]


def _plan_text(question: str) -> str:
    return (
        "Understood. Plan: (1) search flight options, (2) shortlist hotels near "
        f"the requested area, (3) check the travel-policy notes, then compose an "
        f"itinerary for: {question!r}"
    )


def _make_trace(
    started: datetime, question: str, failure: str | None
) -> tuple[TraceIn, list[SpanIn]]:
    """One run of the travel-concierge pipeline. `failure` ∈ {None, "tool",
    "llm", "guardrail"}."""
    trace_id = _hex(32)
    root_id = _hex(16)
    t = started

    def step(seconds: float) -> tuple[datetime, datetime]:
        nonlocal t
        start = t
        t = t + timedelta(seconds=seconds)
        return start, t

    spans: list[SpanIn] = []

    # LLM: plan
    s, e = step(rng.uniform(1.2, 3.0))
    plan_in_tokens = rng.randint(650, 900)
    plan_out_tokens = rng.randint(150, 320)
    spans.append(
        SpanIn(
            trace_id=trace_id,
            span_id=_hex(16),
            parent_span_id=root_id,
            name="plan-itinerary",
            kind="LLM",
            status="ok",
            started_at=s,
            ended_at=e,
            model="claude-opus-5",
            input={
                "system": "You are a travel concierge. Plan before acting.",
                "messages": [{"role": "user", "content": question}],
            },
            output={"role": "assistant", "content": _plan_text(question)},
            input_tokens=plan_in_tokens,
            output_tokens=plan_out_tokens,
            attributes={"temperature": None, "effort": "medium"},
        )
    )

    # TOOL: search_flights
    s, e = step(rng.uniform(0.8, 2.4))
    flight_fail = failure == "tool"
    spans.append(
        SpanIn(
            trace_id=trace_id,
            span_id=_hex(16),
            parent_span_id=root_id,
            name="search_flights",
            kind="TOOL",
            status="error" if flight_fail else "ok",
            started_at=s,
            ended_at=e,
            input={"origin": "BER", "destination": "auto", "flexible_dates": True},
            output=None
            if flight_fail
            else {
                "results": [
                    {"carrier": "LH", "price_eur": rng.randint(120, 480), "stops": 0},
                    {"carrier": "AF", "price_eur": rng.randint(110, 430), "stops": 1},
                ]
            },
            error=SpanErrorIn(
                type="UpstreamTimeout",
                message="flights-api: request timed out after 10s",
                stacktrace=(
                    "Traceback (most recent call last):\n"
                    '  File "tools/flights.py", line 44, in search\n'
                    "    response = client.get(url, timeout=10)\n"
                    "httpx.ReadTimeout: timed out"
                ),
            )
            if flight_fail
            else None,
            attributes={"provider": "flights-api", "retries": 2 if flight_fail else 0},
        )
    )

    if not flight_fail:
        # TOOL: search_hotels
        s, e = step(rng.uniform(0.6, 1.8))
        spans.append(
            SpanIn(
                trace_id=trace_id,
                span_id=_hex(16),
                parent_span_id=root_id,
                name="search_hotels",
                kind="TOOL",
                status="ok",
                started_at=s,
                ended_at=e,
                input={"stars": 4, "max_price_eur": 220},
                output={
                    "results": [
                        {"name": "Hotel Sakura", "price_eur": rng.randint(90, 210)},
                        {"name": "Grand Plaza", "price_eur": rng.randint(120, 260)},
                    ]
                },
                attributes={"provider": "hotels-api"},
            )
        )

        # RETRIEVER: policy lookup
        s, e = step(rng.uniform(0.2, 0.7))
        spans.append(
            SpanIn(
                trace_id=trace_id,
                span_id=_hex(16),
                parent_span_id=root_id,
                name="policy-lookup",
                kind="RETRIEVER",
                status="ok",
                started_at=s,
                ended_at=e,
                input={"query": "refund and cancellation policy"},
                output={
                    "documents": [
                        {"id": "policy-14", "score": 0.91, "snippet": "Free cancellation…"}
                    ]
                },
                attributes={"index": "policies-v2", "top_k": 3},
            )
        )

        # LLM: compose answer (may fail)
        s, e = step(rng.uniform(1.5, 4.0))
        llm_fail = failure == "llm"
        guardrail_fail = failure == "guardrail"
        compose_in = rng.randint(1600, 2400)
        compose_out = 0 if llm_fail else rng.randint(350, 700)
        spans.append(
            SpanIn(
                trace_id=trace_id,
                span_id=_hex(16),
                parent_span_id=root_id,
                name="compose-answer",
                kind="LLM",
                status="error" if llm_fail else "ok",
                started_at=s,
                ended_at=e,
                model="claude-sonnet-5",
                input={
                    "system": "Summarize the findings into a friendly itinerary.",
                    "messages": [
                        {"role": "user", "content": question},
                        {
                            "role": "user",
                            "content": "Tool results: flights + hotels + policy attached.",
                        },
                    ],
                },
                output=None
                if llm_fail
                else {
                    "role": "assistant",
                    "content": (
                        "Here's your itinerary: outbound LH flight, 4★ hotel near the "
                        "centre, and free cancellation up to 48h before check-in. "
                        "Total estimate within budget."
                    ),
                },
                input_tokens=compose_in,
                output_tokens=compose_out or None,
                error=SpanErrorIn(
                    type="RateLimitError",
                    message="model provider returned 429: rate limit exceeded",
                    stacktrace=(
                        "Traceback (most recent call last):\n"
                        '  File "agent/llm.py", line 88, in complete\n'
                        "    response = client.messages.create(**request)\n"
                        "anthropic.RateLimitError: Error code: 429"
                    ),
                )
                if llm_fail
                else None,
                attributes={"effort": "high"},
            )
        )

        if guardrail_fail:
            s, e = step(rng.uniform(0.1, 0.3))
            spans.append(
                SpanIn(
                    trace_id=trace_id,
                    span_id=_hex(16),
                    parent_span_id=root_id,
                    name="output-guardrail",
                    kind="GUARDRAIL",
                    status="error",
                    started_at=s,
                    ended_at=e,
                    input={"check": "pii-and-payment-data"},
                    output={"verdict": "blocked", "rule": "payment-card-number"},
                    error=SpanErrorIn(
                        type="GuardrailViolation",
                        message="response blocked: detected a card-number pattern",
                    ),
                    events=[
                        {
                            "name": "guardrail.blocked",
                            "timestamp": e.isoformat(),
                            "attributes": {"rule": "payment-card-number"},
                        }
                    ],
                )
            )

    # AGENT root span wraps everything
    failed = failure is not None
    spans.insert(
        0,
        SpanIn(
            trace_id=trace_id,
            span_id=root_id,
            parent_span_id=None,
            name="travel-concierge",
            kind="AGENT",
            status="error" if failed else "ok",
            started_at=started,
            ended_at=t,
            input={"question": question},
            output=None if failed else {"itinerary": "delivered"},
            error=SpanErrorIn(
                type="AgentRunFailed", message=f"pipeline failed at the {failure} step"
            )
            if failed
            else None,
        ),
    )

    trace = TraceIn(
        trace_id=trace_id,
        name="travel-concierge",
        session_id=rng.choice(SESSION_IDS),
        metadata={"env": "production", "agent_version": "1.4.2", "region": "eu-central"},
        status="error" if failed else "ok",
    )
    return trace, spans


async def _seed_scores(db, project: Project, trace_in: TraceIn, failed: bool) -> None:
    """Quality signals a real deployment would collect: an automated relevance
    score on every run, plus end-user feedback on some of them."""
    trace = (
        await db.execute(
            select(Trace).where(
                Trace.project_id == project.id, Trace.trace_id == trace_in.trace_id
            )
        )
    ).scalar_one()
    relevance = rng.uniform(0.15, 0.45) if failed else rng.uniform(0.72, 0.98)
    scores = [ScoreBase(name="answer_relevance", value=round(relevance, 2))]
    if rng.random() < 0.6:
        scores.append(
            ScoreBase(
                name="user_feedback",
                value=not failed and rng.random() < 0.9,
                comment=None if not failed else "It never gave me an itinerary.",
            )
        )
    if not failed:
        scores.append(ScoreBase(name="tone", value=rng.choice(["friendly", "friendly", "formal"])))
    for data in scores:
        await upsert_score(
            db,
            project_id=project.id,
            trace_pk=trace.id,
            span_pk=None,
            data=data,
            source="api" if data.name == "user_feedback" else "evaluator",
        )


async def _seed_evals(db, project: Project) -> int:
    """A dataset, a few evaluators, and two prompt experiments to compare.

    Runs on the built-in simulator, so it needs no provider key. Returns the
    number of experiments created (0 when the demo dataset already exists).
    """
    existing = await db.execute(
        select(Dataset.id).where(Dataset.project_id == project.id, Dataset.name == DEMO_DATASET)
    )
    if existing.first() is not None:
        return 0
    dataset = Dataset(
        project_id=project.id,
        name=DEMO_DATASET,
        description="Trip requests with the reply each one should lead with.",
    )
    db.add(dataset)
    await db.flush()
    cases = [
        DatasetItem(
            dataset_id=dataset.id,
            project_id=project.id,
            input={"question": question},
            expected_output=_plan_text(question),
        )
        for question in USER_QUESTIONS
    ]
    db.add_all(cases)
    evaluators = [
        Evaluator(project_id=project.id, name="correctness", template="correctness", config={}),
        Evaluator(project_id=project.id, name="relevance", template="relevance", config={}),
        Evaluator(
            project_id=project.id,
            name="mentions-plan",
            template="contains",
            config={"substring": "plan", "ignore_case": True},
        ),
        Evaluator(
            project_id=project.id,
            name="searched-flights",
            template="required_tools",
            config={"tools": ["search_flights"]},
        ),
    ]
    db.add_all(evaluators)
    await db.flush()
    scored_by = [str(e.id) for e in evaluators[:3]]
    system = "You are a travel concierge. Plan before acting."
    variants = [
        ("concierge-prompt-v1", "{{input.question}}"),
        ("concierge-prompt-v2", "Write a step-by-step plan for this request: {{input.question}}"),
    ]
    for name, user_prompt in variants:
        experiment = Experiment(
            project_id=project.id,
            dataset_id=dataset.id,
            name=name,
            target={
                "type": "prompt",
                "model": "claude-opus-5-5",
                "system": system,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            evaluator_ids=scored_by,
        )
        db.add(experiment)
        await db.flush()
        db.add_all(
            ExperimentItem(
                experiment_id=experiment.id,
                project_id=project.id,
                dataset_item_id=case.id,
                input=case.input,
                expected_output=case.expected_output,
            )
            for case in cases
        )
        await enqueue(db, JOB_KIND, {"experiment_id": str(experiment.id)}, project_id=project.id)
    await db.commit()
    await drain_jobs()
    return len(variants)


async def seed(trace_count: int = 18) -> None:
    configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    factory = get_session_factory()
    async with factory() as db:
        # Demo user
        user = (
            await db.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        password = os.environ.get("DEMO_PASSWORD", "demo-password")
        if user is None:
            user = User(
                email=DEMO_EMAIL, name=DEMO_NAME, password_hash=hash_password(password)
            )
            db.add(user)
            await db.flush()

        # Demo project
        project = (
            await db.execute(
                select(Project).where(
                    Project.owner_id == user.id, Project.name == "Travel Concierge"
                )
            )
        ).scalar_one_or_none()
        if project is None:
            project = Project(
                owner_id=user.id,
                name="Travel Concierge",
                description="Demo agent that plans trips: flights, hotels, and policies.",
            )
            db.add(project)
            await db.flush()

        # Fresh API key each run (previous ones stay valid)
        plaintext, key_hash, prefix = generate_api_key()
        db.add(
            ApiKey(
                project_id=project.id,
                name=f"seed-{datetime.now(UTC):%Y%m%d-%H%M%S}",
                key_hash=key_hash,
                key_prefix=prefix,
            )
        )
        await db.commit()

        existing = (
            await db.execute(
                select(func.count()).select_from(Trace).where(Trace.project_id == project.id)
            )
        ).scalar_one()

        generated = 0
        if existing == 0 or "--more" in sys.argv:
            now = datetime.now(UTC)
            failures = ["tool", "llm", "guardrail"]
            for i in range(trace_count):
                started = now - timedelta(
                    minutes=rng.uniform(5, 60 * 22)  # spread over ~22 hours
                )
                failure = failures[i % 5] if i % 5 < 3 and i % 2 == 0 else None
                trace_in, spans = _make_trace(started, rng.choice(USER_QUESTIONS), failure)
                await ingest_batch(db, project, [trace_in], spans)
                await _seed_scores(db, project, trace_in, failed=failure is not None)
                generated += 1
            await db.commit()

        experiments = await _seed_evals(db, project)

    print("─" * 62)
    print("Demo data ready")
    print(f"  Sign in at the web UI with:  {DEMO_EMAIL} / {password}")
    print(f"  Project:                     {project.name}")
    print(f"  New API key (for the SDK):   {plaintext}")
    print(f"  Traces generated this run:   {generated}")
    print(f"  Experiments run this run:    {experiments}")
    print("─" * 62)


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
