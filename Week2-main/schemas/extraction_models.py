from __future__ import annotations

from typing import Literal, Optional, Union, List, Annotated
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


Number = Optional[float]


class BaseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: str
    company_code: str
    company_name: str
    pdf_page: Optional[int]
    evidence_text: str
    review_status: Literal["pass", "manual_review"] = "manual_review"

    @field_validator("company_code", "company_name", "evidence_text", mode="before")
    @classmethod
    def empty_string_to_none_for_required(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("evidence_text")
    @classmethod
    def evidence_text_not_empty(cls, v: str):
        if not v or not v.strip():
            raise ValueError("evidence_text 不能为空，且必须为原文证据")
        return v


class SubscriptionFlow(BaseRecord):
    record_type: Literal["subscription_flow"]
    increase_date: Optional[str] = None
    subscriber: Optional[str] = None
    subscribed_shares_10k: Number = None
    subscribed_amount_10k_rmb: Number = None
    subscription_price_rmb_per_share: Number = None

    @field_validator("increase_date", "subscriber", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        if v == "":
            return None
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def mark_empty_subscriber_review(self):
        if not self.subscriber:
            self.review_status = "manual_review"
        return self


class EquitySnapshot(BaseRecord):
    record_type: Literal["equity_snapshot"]
    snapshot_time: Optional[str] = None
    equity_basis: Optional[str] = None
    total_shares_10k: Number = None
    total_registered_capital_10k_rmb: Number = None
    shareholder_name: Optional[str] = None
    shares_10k: Number = None
    capital_contribution_10k_rmb: Number = None
    shareholding_ratio: Optional[str] = None

    @field_validator("snapshot_time", "equity_basis", "shareholder_name", "shareholding_ratio", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        if v == "":
            return None
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def mark_empty_shareholder_review(self):
        if not self.shareholder_name:
            self.review_status = "manual_review"
        return self


FactRecord = Annotated[Union[SubscriptionFlow, EquitySnapshot], Field(discriminator="record_type")]


class LLMExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: List[FactRecord] = Field(default_factory=list)
