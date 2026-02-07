"""Subscription management API endpoints."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import auth

from ..auth.middleware import verify_firebase_token
from ..models.subscription import (
    CheckoutRequest,
    CheckoutResponse,
    PortalResponse,
    SubscriptionInfo,
    SubscriptionStatusResponse,
    UsageInfo,
)
from ..services.stripe_service import StripeService
from ..services.subscription_repository import SubscriptionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscription", tags=["subscription"])

# Free tier limits
FREE_TIER_LIMIT = 5


def get_stripe_service() -> StripeService:
    """Get Stripe service instance."""
    api_key = os.getenv("STRIPE_SECRET_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500, detail="Stripe not configured"
        )
    return StripeService(api_key)


def get_subscription_repo() -> SubscriptionRepository:
    """Get subscription repository instance."""
    return SubscriptionRepository()


def get_tier_from_price_id(price_id: str) -> str:
    """Map Stripe price ID to tier name.

    Args:
        price_id: Stripe price ID

    Returns:
        Tier name: "pro" or "enterprise"
    """
    price_tiers = {
        os.getenv("STRIPE_PRICE_ID_PRO"): "pro",
        os.getenv("STRIPE_PRICE_ID_ENTERPRISE"): "enterprise",
    }
    return price_tiers.get(price_id, "pro")


@router.get("/status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    current_user: dict = Depends(verify_firebase_token),
    repo: SubscriptionRepository = Depends(get_subscription_repo),
):
    """Get current user's subscription status and usage.

    Returns:
        Subscription status including tier, usage, and billing info
    """
    try:
        firebase_uid = current_user["uid"]

        # Ensure user exists in database
        from fastapi.concurrency import run_in_threadpool

        user = await run_in_threadpool(repo.get_user, firebase_uid)
        if not user:
            # Create user record
            user_record = auth.get_user(firebase_uid)
            user = await run_in_threadpool(
                repo.create_or_update_user,
                firebase_uid,
                user_record.email or "unknown@example.com"
            )

        current_month = datetime.now().strftime("%Y-%m")

        # Get subscription and usage (synchronous Firestore calls in threadpool)
        subscription = await run_in_threadpool(
            repo.get_active_subscription, firebase_uid
        )
        usage = await run_in_threadpool(
            repo.get_usage, firebase_uid, current_month
        )
        export_count = usage["exportCount"] if usage else 0

        # Determine tier and limits
        if subscription and subscription.get("status") == "active":
            tier = subscription.get("tier", "free")
            limit = None  # Unlimited for paid tiers
            unlimited = True
            status = subscription.get("status")

            subscription_info = SubscriptionInfo(
                current_period_end=subscription["currentPeriodEnd"],
                cancel_at_period_end=subscription.get("cancelAtPeriodEnd", False),
            )
        else:
            tier = "free"
            limit = FREE_TIER_LIMIT
            unlimited = False
            status = "none"
            subscription_info = None

        return SubscriptionStatusResponse(
            tier=tier,
            status=status,
            usage=UsageInfo(
                exports_this_month=export_count,
                limit=limit,
                unlimited=unlimited,
            ),
            subscription=subscription_info,
        )

    except Exception as e:
        logger.error(f"Failed to get subscription status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    current_user: dict = Depends(verify_firebase_token),
    repo: SubscriptionRepository = Depends(get_subscription_repo),
    stripe_service: StripeService = Depends(get_stripe_service),
):
    """Create Stripe checkout session for subscription purchase.

    Args:
        request: Checkout request with price ID and redirect URLs

    Returns:
        Checkout session URL
    """
    try:
        firebase_uid = current_user["uid"]

        # Get or create user
        from fastapi.concurrency import run_in_threadpool

        user = await run_in_threadpool(repo.get_user, firebase_uid)
        if not user:
            user_record = auth.get_user(firebase_uid)
            user = await run_in_threadpool(
                repo.create_or_update_user,
                firebase_uid,
                user_record.email or "unknown@example.com"
            )

        # Create Stripe customer if doesn't exist
        if not user.get("stripeCustomerId"):
            customer_id = await stripe_service.create_customer(
                email=user["email"],
                firebase_uid=firebase_uid,
            )
            user = await run_in_threadpool(
                repo.create_or_update_user,
                firebase_uid,
                user["email"],
                customer_id
            )
        else:
            customer_id = user["stripeCustomerId"]

        # Create checkout session
        session = await stripe_service.create_checkout_session(
            customer_id=customer_id,
            price_id=request.price_id,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )

        return CheckoutResponse(**session)

    except Exception as e:
        logger.error(f"Failed to create checkout: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    current_user: dict = Depends(verify_firebase_token),
    repo: SubscriptionRepository = Depends(get_subscription_repo),
    stripe_service: StripeService = Depends(get_stripe_service),
):
    """Create Stripe customer portal session for subscription management.

    Returns:
        Customer portal URL
    """
    try:
        firebase_uid = current_user["uid"]

        # Get user
        from fastapi.concurrency import run_in_threadpool

        user = await run_in_threadpool(repo.get_user, firebase_uid)
        if not user or not user.get("stripeCustomerId"):
            raise HTTPException(
                status_code=400,
                detail="No subscription found. Please subscribe first.",
            )

        # Create portal session
        portal = await stripe_service.create_portal_session(
            customer_id=user["stripeCustomerId"],
            return_url="https://powerful-layout-467812-p1.web.app",
        )

        return PortalResponse(**portal)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create portal: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
