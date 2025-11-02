"""Pydantic models for subscription API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    """Request to create Stripe checkout session."""

    price_id: str = Field(..., description="Stripe price ID")
    success_url: str = Field(..., description="URL to redirect after successful payment")
    cancel_url: str = Field(..., description="URL to redirect if payment is canceled")


class CheckoutResponse(BaseModel):
    """Response with checkout session URL."""

    checkout_url: str = Field(..., description="Stripe checkout session URL")
    session_id: str = Field(..., description="Stripe session ID")


class PortalResponse(BaseModel):
    """Response with customer portal URL."""

    portal_url: str = Field(..., description="Stripe customer portal URL")


class UsageInfo(BaseModel):
    """Current usage information."""

    exports_this_month: int = Field(..., description="Number of exports this month")
    limit: Optional[int] = Field(None, description="Monthly export limit (null if unlimited)")
    unlimited: bool = Field(..., description="Whether user has unlimited exports")


class SubscriptionInfo(BaseModel):
    """Subscription details."""

    current_period_end: datetime = Field(..., description="Billing period end date")
    cancel_at_period_end: bool = Field(..., description="Will cancel at period end")


class SubscriptionStatusResponse(BaseModel):
    """Response with subscription status and usage."""

    tier: str = Field(..., description="Subscription tier: free, pro, or enterprise")
    status: str = Field(..., description="Subscription status: active, canceled, past_due, or none")
    usage: UsageInfo = Field(..., description="Current month usage")
    subscription: Optional[SubscriptionInfo] = Field(None, description="Subscription details (null for free tier)")
