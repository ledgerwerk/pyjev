"""Thin Python convenience API over TypeSafe's official SDK."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any

from typesafe_sdk import Choice, Noul, NoulCriteria, Question, Score, TypeSafeClient

from .credentials import get_api_key
from .results import ChoiceResult, NoulResult, ScoreResult


def _request_id(response: Any) -> str | None:
    """Read the SDK's public request-id property when a response has one."""
    try:
        value = response.request_id
    except Exception:  # SDK response fakes and non-HTTP responses may omit metadata.
        return None
    return value if isinstance(value, str) else None


def _validate_choice_criteria(choices: Mapping[str, Any | None] | Sequence[str]) -> dict[str, Any | None]:
    if isinstance(choices, Mapping):
        criteria = dict(choices)
    else:
        labels = list(choices)
        if len(labels) != len(set(labels)):
            raise ValueError("choice sequence contains duplicate labels")
        criteria = {name: None for name in labels}

    if not 2 <= len(criteria) <= 255:
        raise ValueError("choice requires between 2 and 255 options")
    for label in criteria:
        if not isinstance(label, str) or not label.strip():
            raise ValueError("choice labels must be nonempty strings")
    return criteria


def _validate_score_levels(levels: Sequence[Any]) -> list[Any]:
    values = list(levels)
    if not 2 <= len(values) <= 10:
        raise ValueError("score requires between 2 and 10 levels")
    return values


class Jev:
    """Convenience client for common Jev decisions.

    `Jev` deliberately delegates transport, retries, validation, and API semantics to
    `typesafe-sdk`.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: TypeSafeClient | None = None,
    ) -> None:
        if client is not None and any(value is not None for value in (api_key, model, timeout)):
            raise ValueError("api_key, model, and timeout cannot be used with an injected client")
        self._owns_client = client is None
        self._client = (
            client
            if client is not None
            else TypeSafeClient(
                api_key=get_api_key(api_key),
                model=model,
                timeout=timeout,
            )
        )

    @property
    def client(self) -> TypeSafeClient:
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
        criteria: NoulCriteria | None = None
        if true is not None or false is not None:
            criteria = {"true": true, "false": false}

        response = self._client.system_one(
            state=state,
            questions={"answer": Noul(instructions=question, criteria=criteria)},
            model=model,
        )
        answer = response.nouls["answer"]
        return NoulResult(
            value=answer.noul,
            model=response.model,
            usage=response.usage.model_dump(mode="json"),
            raw=answer.model_dump(mode="json"),
            request_id=_request_id(response),
        )

    def choice(
        self,
        question: Any,
        *,
        state: Any,
        choices: Mapping[str, Any | None] | Sequence[str],
        model: str | None = None,
    ) -> ChoiceResult:
        criteria = _validate_choice_criteria(choices)
        response = self._client.system_one(
            state=state,
            questions={"answer": Choice(instructions=question, criteria=criteria)},
            model=model,
        )
        answer = response.choices["answer"]
        return ChoiceResult(
            value=answer.choice,
            confidence=answer.confidence,
            probabilities=dict(answer.probabilities),
            model=response.model,
            usage=response.usage.model_dump(mode="json"),
            raw=answer.model_dump(mode="json"),
            request_id=_request_id(response),
        )

    def score(
        self,
        question: Any,
        *,
        state: Any,
        levels: Sequence[Any],
        model: str | None = None,
    ) -> ScoreResult:
        values = _validate_score_levels(levels)
        response = self._client.system_one(
            state=state,
            questions={"answer": Score(instructions=question, criteria=values)},
            model=model,
        )
        answer = response.scores["answer"]
        return ScoreResult(
            value=answer.score,
            confidence=answer.confidence,
            probabilities=dict(answer.probabilities),
            legend=dict(answer.legend),
            model=response.model,
            usage=response.usage.model_dump(mode="json"),
            raw=answer.model_dump(mode="json"),
            request_id=_request_id(response),
        )

    def decide(
        self,
        name: str,
        *,
        state: Any,
        config: str | Path | None = None,
        model: str | None = None,
    ) -> NoulResult | ChoiceResult | ScoreResult:
        """Evaluate a validated named decision from a TOML configuration."""
        from .decisions import ChoiceDecision, NoulDecision, ScoreDecision, load_decision

        decision = load_decision(name, config)
        effective_model = model if model is not None else decision.model
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
        if isinstance(decision, ScoreDecision):
            return self.score(decision.question, state=state, levels=decision.levels, model=effective_model)
        raise TypeError(f"Unsupported decision type: {type(decision).__name__}")

    def run(
        self,
        *,
        state: Any,
        questions: Mapping[str, Question],
        model: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate several independent typed questions in one request."""
        response = self._client.system_one(state=state, questions=questions, model=model)
        return response.model_dump(mode="json")

    def models(self) -> list[dict[str, Any]]:
        response = self._client.models.list()
        return [model.model_dump(mode="json") for model in response.models]

    def close(self) -> None:
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
