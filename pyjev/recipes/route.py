"""Build typed route proposals without importing or invoking application handlers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ..client import AsyncJev, Jev
from ..decisions import BundleDecision, ChoiceDecision, decision_to_dict
from ..results import BundleResult, ChoiceResult
from ._common import probability, validate_id, validate_model

NO_HANDLER = "__none__"
UNSPECIFIED = "__unspecified__"
MAX_HANDLERS = 254
MAX_ROUTE_QUESTIONS = 255


@dataclass(frozen=True, slots=True)
class RouteArgument:
    """One closed-set handler argument, with no free-form generation."""

    name: str
    description: str
    options: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RouteHandler:
    """A handler description and the closed-set arguments the application may need."""

    id: str
    description: str
    arguments: tuple[RouteArgument, ...] = ()


@dataclass(frozen=True, slots=True)
class RoutePlan:
    """Inspectable speculative handler/argument request."""

    request: str
    handlers: tuple[RouteHandler, ...]
    state: dict[str, Any]
    decision: BundleDecision
    argument_keys: dict[str, dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "handlers": [_handler_dict(handler) for handler in self.handlers],
            "state": self.state,
            "decision": decision_to_dict(self.decision),
            "argument_keys": self.argument_keys,
        }


@dataclass(frozen=True, slots=True)
class RouteResult:
    """Proposed route and selected-handler arguments; never an executed action."""

    status: Literal["none", "proposed"]
    handler: RouteHandler | None
    arguments: dict[str, str | None]
    arguments_complete: bool
    handler_result: ChoiceResult
    argument_results: dict[str, ChoiceResult]
    decision: BundleResult

    @property
    def handler_id(self) -> str | None:
        return self.handler.id if self.handler is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "handler_id": self.handler_id,
            "handler": _handler_dict(self.handler) if self.handler is not None else None,
            "arguments": dict(self.arguments),
            "arguments_complete": self.arguments_complete,
            "handler_result": self.handler_result.to_dict(),
            "argument_results": {key: result.to_dict() for key, result in self.argument_results.items()},
            "decision": self.decision.to_dict(),
        }


def build_route(
    request: str,
    handlers: Sequence[RouteHandler],
    *,
    model: str | None = None,
) -> RoutePlan:
    """Build one handler Choice plus argument Choices for every handler.

    All argument questions are deliberately speculative and share one SDK request. Inspect
    ``plan.to_dict()`` because request text, handler descriptions, and allowed argument
    values are included in the state. The recipe has no handler registry or dispatch API.
    """
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request must be a nonempty string")
    validate_model(model)
    if not isinstance(handlers, (list, tuple)):
        raise TypeError("handlers must be a list or tuple to preserve deterministic ordering")
    normalized = _normalize_handlers(handlers)
    if not normalized:
        raise ValueError("route requires at least one handler")
    if len(normalized) > MAX_HANDLERS:
        raise ValueError(f"route supports at most {MAX_HANDLERS} handlers")
    question_count = 1 + sum(len(handler.arguments) for handler in normalized)
    if question_count > MAX_ROUTE_QUESTIONS:
        raise ValueError(f"route supports at most {MAX_ROUTE_QUESTIONS} total questions per request")

    route_options: dict[str, str | None] = {handler.id: handler.description for handler in normalized}
    route_options[NO_HANDLER] = "No supplied handler is appropriate."
    questions: dict[str, ChoiceDecision] = {
        "handler": ChoiceDecision(
            name="handler",
            question=(
                "Which supplied handler, if any, should receive this request? Select the exact handler ID or none."
            ),
            options=route_options,
        )
    }
    argument_keys: dict[str, dict[str, str]] = {}
    for handler_index, handler in enumerate(normalized):
        per_handler: dict[str, str] = {}
        for argument_index, argument in enumerate(handler.arguments):
            key = f"argument_{handler_index:03d}_{argument_index:03d}"
            per_handler[argument.name] = key
            options: dict[str, str | None] = {option: None for option in argument.options}
            options[UNSPECIFIED] = "The request does not specify this argument."
            questions[key] = ChoiceDecision(
                name=key,
                question=(
                    f"For handler {handler.id!r}, select the {argument.name!r} argument from its allowed values. "
                    "Use __unspecified__ if the request does not contain enough information."
                ),
                options=options,
            )
        argument_keys[handler.id] = per_handler
    state = {
        "request": request,
        "handlers": [_handler_dict(handler) for handler in normalized],
    }
    return RoutePlan(
        request,
        normalized,
        state,
        BundleDecision(name="route", questions=questions, model=model),
        argument_keys,
    )


def interpret_route(plan: RoutePlan, result: BundleResult) -> RouteResult:
    """Interpret typed route evidence without importing or calling a handler."""
    if not isinstance(result, BundleResult):
        raise TypeError("route interpretation requires a BundleResult")
    handler_answer = result.answers.get("handler")
    if not isinstance(handler_answer, ChoiceResult):
        raise ValueError("route result is missing handler Choice")
    if not isinstance(handler_answer.value, str):
        raise ValueError("route returned an invalid handler ID")
    probability(handler_answer.confidence, "handler confidence")
    handlers = {handler.id: handler for handler in plan.handlers}
    if handler_answer.value == NO_HANDLER:
        return RouteResult("none", None, {}, True, handler_answer, {}, result)
    handler = handlers.get(handler_answer.value)
    if handler is None:
        raise ValueError(f"route selected unknown handler {handler_answer.value!r}")

    values: dict[str, str | None] = {}
    argument_results: dict[str, ChoiceResult] = {}
    complete = True
    for argument in handler.arguments:
        key = plan.argument_keys[handler.id][argument.name]
        answer = result.answers.get(key)
        if not isinstance(answer, ChoiceResult):
            raise ValueError(f"route result is missing argument Choice {key!r}")
        probability(answer.confidence, f"confidence for argument {argument.name!r}")
        if not isinstance(answer.value, str) or (answer.value not in argument.options and answer.value != UNSPECIFIED):
            raise ValueError(f"route returned invalid value for argument {argument.name!r}")
        argument_results[argument.name] = answer
        if answer.value == UNSPECIFIED:
            values[argument.name] = None
            complete = False
        else:
            values[argument.name] = answer.value
    return RouteResult("proposed", handler, values, complete, handler_answer, argument_results, result)


def execute_route(jev: Jev, plan: RoutePlan) -> RouteResult:
    result = jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, BundleResult):
        raise TypeError("Jev.evaluate returned a non-bundle result for route")
    return interpret_route(plan, result)


async def aexecute_route(jev: AsyncJev, plan: RoutePlan) -> RouteResult:
    result = await jev.evaluate(plan.decision, state=plan.state)
    if not isinstance(result, BundleResult):
        raise TypeError("AsyncJev.evaluate returned a non-bundle result for route")
    return interpret_route(plan, result)


def route(jev: Jev, request: str, handlers: Sequence[RouteHandler], *, model: str | None = None) -> RouteResult:
    """Build and execute a route proposal using the supplied sync client."""
    return execute_route(jev, build_route(request, handlers, model=model))


async def aroute(
    jev: AsyncJev,
    request: str,
    handlers: Sequence[RouteHandler],
    *,
    model: str | None = None,
) -> RouteResult:
    """Native-async counterpart to :func:`route`; it never dispatches handlers."""
    return await aexecute_route(jev, build_route(request, handlers, model=model))


def _normalize_handlers(handlers: Sequence[RouteHandler]) -> tuple[RouteHandler, ...]:
    normalized: list[RouteHandler] = []
    seen: set[str] = set()
    for item in handlers:
        if not isinstance(item, RouteHandler):
            raise TypeError("handlers must contain RouteHandler objects")
        validate_id(item.id, "handler", reserved={NO_HANDLER})
        if item.id in seen:
            raise ValueError(f"duplicate handler ID: {item.id}")
        if not isinstance(item.description, str) or not item.description.strip():
            raise ValueError(f"handler {item.id!r} description must be nonempty")
        if not isinstance(item.arguments, (list, tuple)):
            raise TypeError(f"handler {item.id!r} arguments must be a list or tuple")
        arguments: list[RouteArgument] = []
        seen_arguments: set[str] = set()
        for argument in item.arguments:
            if not isinstance(argument, RouteArgument):
                raise TypeError("handler arguments must contain RouteArgument objects")
            validate_id(argument.name, "argument", reserved={UNSPECIFIED})
            if argument.name in seen_arguments:
                raise ValueError(f"duplicate argument name {argument.name!r} for handler {item.id!r}")
            if not isinstance(argument.description, str) or not argument.description.strip():
                raise ValueError(f"argument {argument.name!r} description must be nonempty")
            if not isinstance(argument.options, (list, tuple)) or not argument.options:
                raise ValueError(f"argument {argument.name!r} requires a nonempty ordered options list")
            if len(argument.options) > 254:
                raise ValueError(f"argument {argument.name!r} supports at most 254 options")
            options: list[str] = []
            for option in argument.options:
                if not isinstance(option, str) or not option.strip():
                    raise ValueError(f"option for argument {argument.name!r} must be a nonempty string")
                if option == UNSPECIFIED:
                    raise ValueError(f"option {UNSPECIFIED!r} is reserved")
                if option in options:
                    raise ValueError(f"duplicate option {option!r} for argument {argument.name!r}")
                options.append(option)
            arguments.append(RouteArgument(argument.name, argument.description, tuple(options)))
            seen_arguments.add(argument.name)
        normalized.append(RouteHandler(item.id, item.description, tuple(arguments)))
        seen.add(item.id)
    return tuple(normalized)


def _handler_dict(handler: RouteHandler) -> dict[str, Any]:
    return {
        "id": handler.id,
        "description": handler.description,
        "arguments": [
            {"name": argument.name, "description": argument.description, "options": list(argument.options)}
            for argument in handler.arguments
        ],
    }
