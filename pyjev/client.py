"""Thin Python convenience API over TypeSafe's official SDK."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, overload

from typesafe_sdk import Asset, AsyncTypeSafeClient, Question, TypeSafeClient

from .compile import build_choice, build_decision_questions, build_noul, build_score, validate_runtime_decision
from .credentials import get_api_key
from .decisions import BundleDecision, ChoiceDecision, Decision, NoulDecision, ScoreDecision, load_decision
from .results import BundleResult, ChoiceResult, NoulResult, PrimitiveResult, ScoreResult

_IMAGE_HEADERS = {"TypeSafe-Danger-Zone-Images": "true"}


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
        images: bool = False,
        client: TypeSafeClient | None = None,
    ) -> None:
        """Create a client or wrap a caller-owned SDK client.

        An injected client cannot be combined with `api_key`, `model`, or `timeout`,
        and is never closed by :meth:`close`.
        """
        if client is not None and any(value is not None for value in (api_key, model, timeout)):
            raise ValueError("api_key, model, and timeout cannot be used with an injected client")
        self._owns_client = client is None
        self._images = images
        self._client = (
            client if client is not None else TypeSafeClient(api_key=get_api_key(api_key), model=model, timeout=timeout)
        )

    def _system_one(
        self,
        *,
        state: Any,
        questions: Mapping[str, Question],
        model: str | None,
        assets: Mapping[str, Asset] | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {"state": state, "questions": questions, "model": model}
        if assets is not None:
            kwargs["assets"] = assets
        if self._images:
            kwargs["extra_headers"] = _IMAGE_HEADERS
        return self._client.system_one(**kwargs)

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
        assets: Mapping[str, Asset] | None = None,
    ) -> NoulResult:
        """Alias for :meth:`noul`."""
        return self.noul(question, state=state, true=true, false=false, model=model, assets=assets)

    def noul(
        self,
        question: Any,
        *,
        state: Any,
        true: Any | None = None,
        false: Any | None = None,
        model: str | None = None,
        assets: Mapping[str, Asset] | None = None,
    ) -> NoulResult:
        """Evaluate a yes/no question and preserve the probability of true."""
        response = self._system_one(
            state=state,
            questions={"answer": build_noul(question, true=true, false=false)},
            model=model,
            assets=assets,
        )
        return _primitive_result(response, "answer", NoulDecision("answer", str(question), true, false, model))

    def choice(
        self,
        question: Any,
        *,
        state: Any,
        choices: Mapping[str, Any | None] | Sequence[str],
        model: str | None = None,
        assets: Mapping[str, Asset] | None = None,
    ) -> ChoiceResult:
        """Evaluate a closed-set Choice question."""
        criteria = dict(choices) if isinstance(choices, Mapping) else {label: None for label in choices}
        response = self._system_one(
            state=state,
            questions={"answer": build_choice(question, criteria)},
            model=model,
            assets=assets,
        )
        return _primitive_result(response, "answer", ChoiceDecision("answer", str(question), criteria))

    def score(
        self,
        question: Any,
        *,
        state: Any,
        levels: Sequence[Any],
        model: str | None = None,
        assets: Mapping[str, Asset] | None = None,
    ) -> ScoreResult:
        """Evaluate state against an ordered Score rubric."""
        values = list(levels)
        response = self._system_one(
            state=state,
            questions={"answer": build_score(question, values)},
            model=model,
            assets=assets,
        )
        return _primitive_result(response, "answer", ScoreDecision("answer", str(question), tuple(values)))

    def evaluate(
        self,
        decision: Decision,
        *,
        state: Any,
        model: str | None = None,
        assets: Mapping[str, Asset] | None = None,
    ) -> NoulResult | ChoiceResult | ScoreResult | BundleResult:
        """Evaluate a validated in-memory typed decision declaration.

        An explicit ``model`` overrides the declaration's model. A bundle is sent
        in one SDK request and each child is returned as its normal typed result.
        Decision construction and this method's local validation do not resolve
        credentials; only the call to the underlying SDK performs I/O.
        """
        validate_runtime_decision(decision)
        effective_model = model if model is not None else decision.model
        questions = build_decision_questions(decision)
        response = self._system_one(state=state, questions=questions, model=effective_model, assets=assets)
        if isinstance(decision, BundleDecision):
            answers = {name: _primitive_result(response, name, child) for name, child in decision.questions.items()}
            return BundleResult(
                answers=answers,
                model=response.model,
                usage=_usage(response),
                raw=response.model_dump(mode="json"),
                request_id=_request_id(response),
            )
        return _primitive_result(response, "answer", decision)

    def decide(
        self,
        name: str,
        *,
        state: Any,
        config: str | Path | None = None,
        model: str | None = None,
        assets: Mapping[str, Asset] | None = None,
    ) -> NoulResult | ChoiceResult | ScoreResult | BundleResult:
        """Evaluate a named primitive or bundle decision from TOML."""
        decision = load_decision(name, config)
        return self.evaluate(decision, state=state, model=model, assets=assets)

    def _bundle(
        self,
        decision: BundleDecision,
        *,
        state: Any,
        model: str | None,
        assets: Mapping[str, Asset] | None = None,
    ) -> BundleResult:
        questions = build_decision_questions(decision)
        response = self._system_one(state=state, questions=questions, model=model, assets=assets)
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
        assets: Mapping[str, Asset] | None = None,
    ) -> dict[str, Any]:
        """Evaluate several independent SDK questions in one request."""
        response = self._system_one(state=state, questions=questions, model=model, assets=assets)
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
        images: bool = False,
        client: AsyncTypeSafeClient | None = None,
    ) -> None:
        """Create an async client without simulating async over synchronous I/O."""
        if client is not None and any(value is not None for value in (api_key, model, timeout)):
            raise ValueError("api_key, model, and timeout cannot be used with an injected client")
        self._owns_client = client is None
        self._images = images
        self._client = (
            client
            if client is not None
            else AsyncTypeSafeClient(api_key=get_api_key(api_key), model=model, timeout=timeout)
        )

    async def _system_one(
        self,
        *,
        state: Any,
        questions: Mapping[str, Question],
        model: str | None,
        assets: Mapping[str, Asset] | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {"state": state, "questions": questions, "model": model}
        if assets is not None:
            kwargs["assets"] = assets
        if self._images:
            kwargs["extra_headers"] = _IMAGE_HEADERS
        return await self._client.system_one(**kwargs)

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
        assets: Mapping[str, Asset] | None = None,
    ) -> NoulResult:
        """Async alias for :meth:`noul`."""
        return await self.noul(question, state=state, true=true, false=false, model=model, assets=assets)

    async def noul(
        self,
        question: Any,
        *,
        state: Any,
        true: Any | None = None,
        false: Any | None = None,
        model: str | None = None,
        assets: Mapping[str, Asset] | None = None,
    ) -> NoulResult:
        """Evaluate Noul through the native async SDK client."""
        response = await self._system_one(
            state=state,
            questions={"answer": build_noul(question, true=true, false=false)},
            model=model,
            assets=assets,
        )
        return _primitive_result(response, "answer", NoulDecision("answer", str(question), true, false, model))

    async def choice(
        self,
        question: Any,
        *,
        state: Any,
        choices: Mapping[str, Any | None] | Sequence[str],
        model: str | None = None,
        assets: Mapping[str, Asset] | None = None,
    ) -> ChoiceResult:
        """Evaluate Choice through the native async SDK client."""
        criteria = dict(choices) if isinstance(choices, Mapping) else {label: None for label in choices}
        response = await self._system_one(
            state=state,
            questions={"answer": build_choice(question, criteria)},
            model=model,
            assets=assets,
        )
        return _primitive_result(response, "answer", ChoiceDecision("answer", str(question), criteria))

    async def score(
        self,
        question: Any,
        *,
        state: Any,
        levels: Sequence[Any],
        model: str | None = None,
        assets: Mapping[str, Asset] | None = None,
    ) -> ScoreResult:
        """Evaluate Score through the native async SDK client."""
        values = list(levels)
        response = await self._system_one(
            state=state,
            questions={"answer": build_score(question, values)},
            model=model,
            assets=assets,
        )
        return _primitive_result(response, "answer", ScoreDecision("answer", str(question), tuple(values)))

    async def evaluate(
        self,
        decision: Decision,
        *,
        state: Any,
        model: str | None = None,
        assets: Mapping[str, Asset] | None = None,
    ) -> NoulResult | ChoiceResult | ScoreResult | BundleResult:
        """Evaluate an in-memory decision using the native async SDK client.

        An explicit ``model`` overrides the declaration's model. Independent bundle
        questions share one SDK request and retain their primitive result types.
        """
        validate_runtime_decision(decision)
        effective_model = model if model is not None else decision.model
        questions = build_decision_questions(decision)
        response = await self._system_one(state=state, questions=questions, model=effective_model, assets=assets)
        if isinstance(decision, BundleDecision):
            answers = {name: _primitive_result(response, name, child) for name, child in decision.questions.items()}
            return BundleResult(
                answers=answers,
                model=response.model,
                usage=_usage(response),
                raw=response.model_dump(mode="json"),
                request_id=_request_id(response),
            )
        return _primitive_result(response, "answer", decision)

    async def decide(
        self,
        name: str,
        *,
        state: Any,
        config: str | Path | None = None,
        model: str | None = None,
        assets: Mapping[str, Asset] | None = None,
    ) -> NoulResult | ChoiceResult | ScoreResult | BundleResult:
        """Evaluate a named primitive or bundle asynchronously."""
        decision = load_decision(name, config)
        return await self.evaluate(decision, state=state, model=model, assets=assets)

    async def run(
        self,
        *,
        state: Any,
        questions: Mapping[str, Question],
        model: str | None = None,
        assets: Mapping[str, Asset] | None = None,
    ) -> dict[str, Any]:
        """Evaluate several SDK questions asynchronously in one request."""
        response = await self._system_one(state=state, questions=questions, model=model, assets=assets)
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
