"""Thin Python convenience API over TypeSafe's official SDK."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Any

from typesafe_sdk import Choice, Noul, Question, Score, TypeSafeClient

from .credentials import get_api_key
from .results import ChoiceResult, NoulResult, ScoreResult


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
        self._owns_client = client is None
        self._client = client or TypeSafeClient(
            api_key=get_api_key(api_key),
            model=model,
            timeout=timeout,
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
        criteria = None
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
        )

    def choice(
        self,
        question: Any,
        *,
        state: Any,
        choices: Mapping[str, Any | None] | Sequence[str],
        model: str | None = None,
    ) -> ChoiceResult:
        if isinstance(choices, Mapping):
            criteria = dict(choices)
        else:
            criteria = {name: None for name in choices}
        if len(criteria) < 2:
            raise ValueError("choice requires at least two options")

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
        )

    def score(
        self,
        question: Any,
        *,
        state: Any,
        levels: Sequence[Any],
        model: str | None = None,
    ) -> ScoreResult:
        if not levels:
            raise ValueError("score requires at least one level")

        response = self._client.system_one(
            state=state,
            questions={"answer": Score(instructions=question, criteria=list(levels))},
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
        )

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
