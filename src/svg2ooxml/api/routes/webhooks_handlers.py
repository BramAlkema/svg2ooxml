"""Stripe webhook event handlers."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from ..services.subscription_repository import SubscriptionRepository

logger = logging.getLogger(__name__)


def get_tier_from_price_id(price_id: str) -> str:
    """Map Stripe price ID to tier name."""

    price_tiers = {
        os.getenv("STRIPE_PRICE_ID_PRO"): "pro",
        os.getenv("STRIPE_PRICE_ID_ENTERPRISE"): "enterprise",
    }
    return price_tiers.get(price_id, "pro")


async def handle_subscription_created(subscription, repo: SubscriptionRepository) -> None:
    """Handle new subscription creation."""

    user = await repo.get_user_by_stripe_customer(subscription.customer)
    if not user:
        logger.error("User not found for customer %s", subscription.customer)
        return

    price_id = subscription.items.data[0].price.id
    tier = get_tier_from_price_id(price_id)

    await repo.create_or_update_subscription(
        stripe_subscription_id=subscription.id,
        user_id=user["id"],
        stripe_price_id=price_id,
        status=subscription.status,
        tier=tier,
        current_period_start=datetime.fromtimestamp(subscription.current_period_start, tz=UTC),
        current_period_end=datetime.fromtimestamp(subscription.current_period_end, tz=UTC),
        cancel_at_period_end=subscription.cancel_at_period_end,
    )

    logger.info("Created subscription %s for user %s (tier: %s)", subscription.id, user["id"], tier)


async def handle_subscription_updated(subscription, repo: SubscriptionRepository) -> None:
    """Handle subscription update."""

    user = await repo.get_user_by_stripe_customer(subscription.customer)
    if not user:
        logger.error("User not found for customer %s", subscription.customer)
        return

    price_id = subscription.items.data[0].price.id
    tier = get_tier_from_price_id(price_id)

    await repo.create_or_update_subscription(
        stripe_subscription_id=subscription.id,
        user_id=user["id"],
        stripe_price_id=price_id,
        status=subscription.status,
        tier=tier,
        current_period_start=datetime.fromtimestamp(subscription.current_period_start, tz=UTC),
        current_period_end=datetime.fromtimestamp(subscription.current_period_end, tz=UTC),
        cancel_at_period_end=subscription.cancel_at_period_end,
        canceled_at=(
            datetime.fromtimestamp(subscription.canceled_at, tz=UTC)
            if subscription.canceled_at
            else None
        ),
    )

    logger.info("Updated subscription %s (status: %s)", subscription.id, subscription.status)


async def handle_subscription_deleted(subscription, repo: SubscriptionRepository) -> None:
    """Handle subscription deletion/cancellation."""

    user = await repo.get_user_by_stripe_customer(subscription.customer)
    if not user:
        logger.error("User not found for customer %s", subscription.customer)
        return

    price_id = subscription.items.data[0].price.id
    tier = get_tier_from_price_id(price_id)

    await repo.create_or_update_subscription(
        stripe_subscription_id=subscription.id,
        user_id=user["id"],
        stripe_price_id=price_id,
        status="canceled",
        tier=tier,
        current_period_start=datetime.fromtimestamp(subscription.current_period_start, tz=UTC),
        current_period_end=datetime.fromtimestamp(subscription.current_period_end, tz=UTC),
        cancel_at_period_end=True,
        canceled_at=datetime.now(tz=UTC),
    )

    logger.info("Deleted subscription %s", subscription.id)


async def handle_payment_succeeded(invoice, repo: SubscriptionRepository) -> None:  # noqa: ARG001
    """Handle successful payment."""

    subscription_id = invoice.subscription
    if not subscription_id:
        logger.info("Invoice not related to subscription, skipping")
        return

    logger.info(
        "Payment succeeded for subscription %s (amount: %s %s)",
        subscription_id,
        invoice.amount_paid / 100,
        invoice.currency.upper(),
    )


async def handle_payment_failed(invoice, repo: SubscriptionRepository) -> None:  # noqa: ARG001
    """Handle failed payment."""

    subscription_id = invoice.subscription
    if not subscription_id:
        logger.info("Invoice not related to subscription, skipping")
        return

    logger.warning(
        "Payment failed for subscription %s (amount: %s %s)",
        subscription_id,
        invoice.amount_due / 100,
        invoice.currency.upper(),
    )


__all__ = [
    "get_tier_from_price_id",
    "handle_payment_failed",
    "handle_payment_succeeded",
    "handle_subscription_created",
    "handle_subscription_deleted",
    "handle_subscription_updated",
]
