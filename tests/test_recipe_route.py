from __future__ import annotations

import asyncio

import pytest

from pyjev import BundleResult, ChoiceResult
from pyjev.recipes.route import (
    NO_HANDLER,
    UNSPECIFIED,
    RouteArgument,
    RouteHandler,
    RoutePlan,
    aroute,
    build_route,
    interpret_route,
    route,
)


def choice(value: str, confidence: float = 0.9) -> ChoiceResult:
    return ChoiceResult(
        value=value,
        confidence=confidence,
        probabilities={value: confidence},
        model="test-model",
        usage={"input_tokens": 2},
        raw={"choice": value},
        request_id="route-request",
    )


def bundle(values: dict[str, ChoiceResult]) -> BundleResult:
    return BundleResult(values, "test-model", {"input_tokens": 10}, {}, "route-request")


def handlers() -> list[RouteHandler]:
    return [
        RouteHandler(
            "issue",
            "Create or update a support issue",
            (
                RouteArgument("priority", "Ticket priority", ("low", "high priority")),
                RouteArgument("team", "Owning team", ("billing", "technical")),
            ),
        ),
        RouteHandler("docs", "Search internal documentation"),
    ]


def routed_bundle(plan: RoutePlan, *, priority: str = "high priority", team: str = "technical") -> BundleResult:
    return bundle(
        {
            "handler": choice("issue"),
            plan.argument_keys["issue"]["priority"]: choice(priority),
            plan.argument_keys["issue"]["team"]: choice(team),
        }
    )


class FakeJev:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def evaluate(self, decision, *, state):
        self.calls.append((decision, state))
        return self.result


class FakeAsyncJev(FakeJev):
    async def evaluate(self, decision, *, state):
        self.calls.append((decision, state))
        return self.result


def test_route_plan_inspects_handler_and_speculative_argument_questions():
    plan = build_route("Payment failed", handlers(), model="pinned-model")
    assert isinstance(plan, RoutePlan)
    assert list(plan.decision.questions) == ["handler", "argument_000_000", "argument_000_001"]
    assert "__none__" in plan.decision.questions["handler"].options
    assert UNSPECIFIED in plan.decision.questions["argument_000_000"].options
    assert plan.decision.model == "pinned-model"
    assert plan.to_dict()["state"]["request"] == "Payment failed"


def test_route_returns_only_proposal_and_never_invokes_application_handler():
    plan = build_route("Payment failed", handlers())
    selected = routed_bundle(plan)
    fake = FakeJev(selected)
    side_effects = []

    def application_handler(**arguments):
        side_effects.append(arguments)

    result = route(fake, "Payment failed", handlers())
    assert result.status == "proposed"
    assert result.handler_id == "issue"
    assert result.arguments == {"priority": "high priority", "team": "technical"}
    assert result.arguments_complete is True
    assert side_effects == []
    assert len(fake.calls) == 1
    assert fake.calls[0][0].name == "route"
    assert callable(application_handler)


def test_route_preserves_unspecified_argument_and_explicit_none_handler():
    plan = build_route("Incomplete request", handlers())
    incomplete = interpret_route(plan, routed_bundle(plan, priority=UNSPECIFIED))
    assert incomplete.arguments["priority"] is None
    assert incomplete.arguments_complete is False
    none = interpret_route(plan, bundle({"handler": choice(NO_HANDLER)}))
    assert none.status == "none"
    assert none.handler_id is None
    assert none.arguments == {}


def test_route_rejects_invalid_or_oversized_specs_before_evaluation():
    with pytest.raises(ValueError, match="duplicate handler ID"):
        build_route("request", [RouteHandler("same", "one"), RouteHandler("same", "two")])
    too_many = tuple(RouteArgument(f"arg{index}", "argument", ("yes", "no")) for index in range(255))
    with pytest.raises(ValueError, match="total questions"):
        build_route("request", [RouteHandler("handler", "description", too_many)])


def test_aroute_uses_async_evaluator_without_dispatch():
    async def run() -> None:
        plan = build_route("Payment failed", handlers())
        fake = FakeAsyncJev(routed_bundle(plan))
        result = await aroute(fake, "Payment failed", handlers())
        assert result.arguments_complete is True
        assert len(fake.calls) == 1

    asyncio.run(run())
