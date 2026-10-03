"""Structured final answer. The model must submit this via the ``submit_answer`` tool."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AnswerStatus(StrEnum):
    ANSWER = "answer"
    ABSTAIN = "abstain"  # the data needed is missing or incomplete
    REFUSE = "refuse"  # out of policy: advice, predictions, non-allowlisted addresses


class Claim(BaseModel):
    id: str = Field(description="Short id referenced in the text as {id}, e.g. c1")
    value: str = Field(
        description="The number exactly as a tool returned it, digits only, "
        "e.g. 272134858.47907041001 or 787131486.58"
    )
    unit: str = Field(description="Token symbol (UNI, ETH, USDC...), USD, count, or percent")
    description: str = Field(description="What the number is, without repeating the number")
    source_call_ids: list[str] = Field(description="call_id(s) of the tool results it comes from")
    tx_hashes: list[str] = Field(
        default_factory=list, description="Supporting tx hashes from those results, if any"
    )


class FinalAnswer(BaseModel):
    status: AnswerStatus
    text: str = Field(
        description="Answer in plain English. Refer to every number with its "
        "claim placeholder like {c1}; do not write numbers directly."
    )
    claims: list[Claim] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    missing: str | None = Field(
        None,
        description="For abstain/refuse: exactly what is missing "
        "or why the request is out of scope",
    )
