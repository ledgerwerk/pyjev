"""Thin Python convenience API over TypeSafe's official SDK."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, overload

from typesafe_sdk import AsyncTypeSafeClient, Question, TypeSafeClient

from .compile import build_choice, build_decision_questions, build_noul, build_score
from .credentials import get_api_key
from .decisions import BundleDecision, ChoiceDecision, NoulDecision, ScoreDecision, load_decision
from .results import BundleResult, ChoiceResult, NoulResult, PrimitiveResult, ScoreResult


def _request_id(response: Any) -> str | None:
    """Read the SDK's public request-id property when a response has one."""
    try:
        value = response.request_id
    except Exception:  # SDK response fakes and non-HTTP responses may omit metadata.
        return None
    return value if isinstance(value, str) else None


def _usage(response: Any) -> dict[str, Any]:
    return response.usage.model_dump(mode="json")


@overload
def _primitive_result(response: Any, name: str, decision: NoulDecision) -> NoulResult: ...
@overload
def _primitive_result(response: Any, name: str, decision: ChoiceDecision) -> ChoiceResult: ...
@overload
def _primitive_result(response: Any, name: str, decision: ScoreDecision) -> ScoreResult: ...


def _primitive_result(
    response: Any,
    name: str,
    decision: NoulDecision | ChoiceDecision | ScoreDecision,
) -> PrimitiveResult:
    request_id = _request_id(response)
    if isinstance(decision, NoulDecision):
        answer = response.nouls[name]
        return NoulResult(
            value=answer.noul,
            model=response.model,
            usage=_usage(response),
            raw=answer.model_dump(mode="json"),
            request_id=request_id,
        )
    if isinstance(decision, ChoiceDecision):
        answer = response.choices[name]
        return ChoiceResult(
            value=answer.choice,
            confidence=answer.confidence,
            probabilities=dict(answer.probabilities),
            model=response.model,
            usage=_usage(response),
            raw=answer.model_dump(mode="json"),
            request_id=request_id,
        )
    answer = response.scores[name]
    return ScoreResult(
        value=answer.score,
        confidence=answer.confidence,
        probabilities=dict(answer.probabilities),
        legend=dict(answer.legend),
        model=response.model,
        usage=_usage(response),
        raw=answer.model_dump(mode="json"),
        request_id=request_id,
    )


class Jev:
    """Convenience client for common Jev decisions.

    `Jev` deliberately delegates transport, retries, validation, and API semantics to
    `typesafe-sdk`. It only adds ergonomic request construction and result wrappers.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: TypeSafeClient | None = None,
    ) -> None:
        """Create a client or wrap a caller-owned SDK client.

        An injected client cannot be combined with `api_key`, `model`, or `timeout`,
        and is never closed by :meth:`close`.
        """
        if client is not None and any(value is not None for value in (api_key, model, timeout)):
            raise ValueError("api_key, model, and timeout cannot be used with an injected client")
        self._owns_client = client is None
        self._client = (
            client if client is not None else TypeSafeClient(api_key=get_api_key(api_key), model=model, timeout=timeout)
        )

    @property
    def client(self) -> TypeSafeClient:
        """Return the underlying SDK client."""
        return self._client

    def ask(
        self,
        question: Any,
        *,
        state: Any,
        true: Any | None = None,
        false: Any | None = None,
        model: str | None = None,
    ) -> NoulResult:
        """Alias for :meth:`noul`."""
        return self.noul(question, state=state, true=true, false=false, model=model)

    def noul(
        self,
        question: Any,
        *,
        state: Any,
        true: Any | None = None,
        false: Any | None = None,
        model: str | None = None,
    ) -> NoulResult:
        """Evaluate a yes/no question and preserve the probability of true."""
        response = self._client.system_one(
            state=state,
            questions={"answer": build_noul(question, true=true, false=false)},
            model=model,
        )
        return _primitive_result(response, "answer", NoulDecision("answer", str(question), true, false, model))

    def choice(
        self,
        question: Any,
        *,
        state: Any,
        choices: Mapping[str, Any | None] | Sequence[str],
        model: str | None = None,
    ) -> ChoiceResult:
        """Evaluate a closed-set Choice question."""
        criteria = dict(choices) if isinstance(choices, Mapping) else {label: None for label in choices}
        response = self._client.system_one(
            state=state,
            questions={"answer": build_choice(question, criteria)},
            model=model,
        )
        return _primitive_result(response, "answer", ChoiceDecision("answer", str(question), criteria))

    def score(
        self,
        question: Any,
        *,
        state: Any,
        levels: Sequence[Any],
        model: str | None = None,
    ) -> ScoreResult:
        """Evaluate state against an ordered Score rubric."""
        values = list(levels)
        response = self._client.system_one(
            state=state,
            questions={"answer": build_score(question, values)},
            model=model,
        )
        return _primitive_result(response, "answer", ScoreDecision("answer", str(question), tuple(values)))

    def decide(
        self,
        name: str,
        *,
        state: Any,
        config: str | Path | None = None,
        model: str | None = None,
    ) -> NoulResult | ChoiceResult | ScoreResult | BundleResult:
        """Evaluate a named primitive or bundle decision from TOML."""
        decision = load_decision(name, config)
        effective_model = model if model is not None else decision.model
        if isinstance(decision, BundleDecision):
            return self._bundle(decision, state=state, model=effective_model)
        if isinstance(decision, NoulDecision):
            return self.noul(
                decision.question,
                state=state,
                true=decision.true,
                false=decision.false,
                model=effective_model,
            )
        if isinstance(decision, ChoiceDecision):
            return self.choice(decision.question, state=state, choices=decision.options, model=effective_model)
        return self.score(decision.question, state=state, levels=decision.levels, model=effective_model)

    def _bundle(self, decision: BundleDecision, *, state: Any, model: str | None) -> BundleResult:
        questions = build_decision_questions(decision)
        response = self._client.system_one(state=state, questions=questions, model=model)
        answers = {name: _primitive_result(response, name, child) for name, child in decision.questions.items()}
        return BundleResult(
            answers=answers,
            model=response.model,
            usage=_usage(response),
            raw=response.model_dump(mode="json"),
            request_id=_request_id(response),
        )

    def run(
        self,
        *,
        state: Any,
        questions: Mapping[str, Question],
        model: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate several independent SDK questions in one request."""
        response = self._client.system_one(state=state, questions=questions, model=model)
        return response.model_dump(mode="json")

    def models(self) -> list[dict[str, Any]]:
        """List models using the underlying SDK client."""
        response = self._client.models.list()
        return [model.model_dump(mode="json") for model in response.models]

    def auth_test(self) -> NoulResult:
        """Perform one minimal official-SDK request to verify authentication."""
        return self.noul(
            "Is this an authentication test?",
            state="authentication test",
        )

    def close(self) -> None:
        """Close only a client created by this instance."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Jev:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class AsyncJev:
    """Native async counterpart to :class:`Jev` using the SDK async client."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: AsyncTypeSafeClient | None = None,
    ) -> None:
        """Create an async client without simulating async over synchronous I/O."""
        if client is not None and any(value is not None for value in (api_key, model, timeout)):
            raise ValueError("api_key, model, and timeout cannot be used with an injected client")
        self._owns_client = client is None
        self._client = (
            client
            if client is not None
            else AsyncTypeSafeClient(api_key=get_api_key(api_key), model=model, timeout=timeout)
        )

    @property
    def client(self) -> AsyncTypeSafeClient:
        """Return the underlying native async SDK client."""
        return self._client

    async def ask(
        self,
        question: Any,
        *,
        state: Any,
        true: Any | None = None,
        false: Any | None = None,
        model: str | None = None,
    ) -> NoulResult:
        """Async alias for :meth:`noul`."""
        return await self.noul(question, state=state, true=true, false=false, model=model)

    async def noul(
        self,
        question: Any,
        *,
        state: Any,
        true: Any | None = None,
        false: Any | None = None,
        model: str | None = None,
    ) -> NoulResult:
        """Evaluate Noul through the native async SDK client."""
        response = await self._client.system_one(
            state=state,
            questions={"answer": build_noul(question, true=true, false=false)},
            model=model,
        )
        return _primitive_result(response, "answer", NoulDecision("answer", str(question), true, false, model))

    async def choice(
        self,
        question: Any,
        *,
        state: Any,
        choices: Mapping[str, Any | None] | Sequence[str],
        model: str | None = None,
    ) -> ChoiceResult:
        """Evaluate Choice through the native async SDK client."""
        criteria = dict(choices) if isinstance(choices, Mapping) else {label: None for label in choices}
        response = await self._client.system_one(
            state=state,
            questions={"answer": build_choice(question, criteria)},
            model=model,
        )
        return _primitive_result(response, "answer", ChoiceDecision("answer", str(question), criteria))

    async def score(
        self,
        question: Any,
        *,
        state: Any,
        levels: Sequence[Any],
        model: str | None = None,
    ) -> ScoreResult:
        """Evaluate Score through the native async SDK client."""
        values = list(levels)
        response = await self._client.system_one(
            state=state,
            questions={"answer": build_score(question, values)},
            model=model,
        )
        return _primitive_result(response, "answer", ScoreDecision("answer", str(question), tuple(values)))

    async def decide(
        self,
        name: str,
        *,
        state: Any,
        config: str | Path | None = None,
        model: str | None = None,
    ) -> NoulResult | ChoiceResult | ScoreResult | BundleResult:
        """Evaluate a named primitive or bundle asynchronously."""
        decision = load_decision(name, config)
        effective_model = model if model is not None else decision.model
        if isinstance(decision, BundleDecision):
            questions = build_decision_questions(decision)
            response = await self._client.system_one(state=state, questions=questions, model=effective_model)
            answers = {name: _primitive_result(response, name, child) for name, child in decision.questions.items()}
            return BundleResult(
                answers=answers,
                model=response.model,
                usage=_usage(response),
                raw=response.model_dump(mode="json"),
                request_id=_request_id(response),
            )
        if isinstance(decision, NoulDecision):
            return await self.noul(
                decision.question,
                state=state,
                true=decision.true,
                false=decision.false,
                model=effective_model,
            )
        if isinstance(decision, ChoiceDecision):
            return await self.choice(
                decision.question,
                state=state,
                choices=decision.options,
                model=effective_model,
            )
        return await self.score(decision.question, state=state, levels=decision.levels, model=effective_model)

    async def run(
        self,
        *,
        state: Any,
        questions: Mapping[str, Question],
        model: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate several SDK questions asynchronously in one request."""
        response = await self._client.system_one(state=state, questions=questions, model=model)
        return response.model_dump(mode="json")

    async def models(self) -> list[dict[str, Any]]:
        """List models through the native async SDK client."""
        response = await self._client.models.list()
        return [model.model_dump(mode="json") for model in response.models]

    async def close(self) -> None:
        """Close only a client created by this instance."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncJev:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
