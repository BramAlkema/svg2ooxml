"""Webhook handlers for external services."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from firebase_admin import firestore
import stripe

from ..services.stripe_service import StripeService
from ..services.subscription_repository import SubscriptionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])

# Lazy-initialized Firestore client (initialized after Firebase app setup in main.py)
_db = None


def get_webhook_db():
    """Get or create Firestore client for webhook idempotency tracking."""
    global _db
    if _db is None:
        _db = firestore.client()
    return _db


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


@router.post("/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events.

    Processes subscription lifecycle events:
    - customer.subscription.created
    - customer.subscription.updated
    - customer.subscription.deleted
    - invoice.payment_succeeded
    - invoice.payment_failed
    """
    try:
        # Get raw payload and signature
        payload = await request.body()
        signature = request.headers.get("stripe-signature")

        if not signature:
            raise HTTPException(status_code=400, detail="Missing signature")

        # Verify webhook signature
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        if not webhook_secret:
            logger.error("STRIPE_WEBHOOK_SECRET not configured")
            raise HTTPException(status_code=500, detail="Webhook not configured")

        stripe_service = StripeService(os.getenv("STRIPE_SECRET_KEY"))
        event = stripe_service.verify_webhook_signature(
            payload, signature, webhook_secret
        )

        # Check for replay attacks using idempotency
        event_id = event.id
        db = get_webhook_db()
        webhook_events_collection = db.collection("webhook_events")
        event_ref = webhook_events_collection.document(event_id)
        event_doc = event_ref.get()

        if event_doc.exists:
            logger.info(f"Webhook event {event_id} already processed (idempotent replay)")
            return {"status": "ok", "message": "already_processed"}

        # Mark event as processed (with 24-hour TTL for cleanup)
        event_ref.set({
            "event_id": event_id,
            "event_type": event.type,
            "processed_at": firestore.SERVER_TIMESTAMP,
            "expires_at": datetime.now(timezone.utc).timestamp() + 86400,  # 24 hours
        })

        # Get repository
        repo = SubscriptionRepository()

        # Handle different event types
        if event.type == "customer.subscription.created":
            await handle_subscription_created(event.data.object, repo)

        elif event.type == "customer.subscription.updated":
            await handle_subscription_updated(event.data.object, repo)

        elif event.type == "customer.subscription.deleted":
            await handle_subscription_deleted(event.data.object, repo)

        elif event.type == "invoice.payment_succeeded":
            await handle_payment_succeeded(event.data.object, repo)

        elif event.type == "invoice.payment_failed":
            await handle_payment_failed(event.data.object, repo)

        else:
            logger.info(f"Unhandled event type: {event.type}")

        return {"status": "ok"}

    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def handle_subscription_created(subscription, repo: SubscriptionRepository):
    """Handle new subscription creation.

    Args:
        subscription: Stripe subscription object
        repo: Subscription repository
    """
    try:
        # Get user by Stripe customer ID
        user = await repo.get_user_by_stripe_customer(subscription.customer)
        if not user:
            logger.error(f"User not found for customer {subscription.customer}")
            return

        # Determine tier from price ID
        price_id = subscription.items.data[0].price.id
        tier = get_tier_from_price_id(price_id)

        # Create subscription record
        await repo.create_or_update_subscription(
            stripe_subscription_id=subscription.id,
            user_id=user["id"],
            stripe_price_id=price_id,
            status=subscription.status,
            tier=tier,
            current_period_start=datetime.fromtimestamp(
                subscription.current_period_start, tz=timezone.utc
            ),
            current_period_end=datetime.fromtimestamp(
                subscription.current_period_end, tz=timezone.utc
            ),
            cancel_at_period_end=subscription.cancel_at_period_end,
        )

        logger.info(
            f"Created subscription {subscription.id} for user {user['id']} (tier: {tier})"
        )

    except Exception as e:
        logger.error(f"Failed to handle subscription created: {e}")
        raise


async def handle_subscription_updated(subscription, repo: SubscriptionRepository):
    """Handle subscription update.

    Args:
        subscription: Stripe subscription object
        repo: Subscription repository
    """
    try:
        # Get user by Stripe customer ID
        user = await repo.get_user_by_stripe_customer(subscription.customer)
        if not user:
            logger.error(f"User not found for customer {subscription.customer}")
            return

        # Determine tier from price ID
        price_id = subscription.items.data[0].price.id
        tier = get_tier_from_price_id(price_id)

        # Update subscription record
        await repo.create_or_update_subscription(
            stripe_subscription_id=subscription.id,
            user_id=user["id"],
            stripe_price_id=price_id,
            status=subscription.status,
            tier=tier,
            current_period_start=datetime.fromtimestamp(
                subscription.current_period_start, tz=timezone.utc
            ),
            current_period_end=datetime.fromtimestamp(
                subscription.current_period_end, tz=timezone.utc
            ),
            cancel_at_period_end=subscription.cancel_at_period_end,
            canceled_at=(
                datetime.fromtimestamp(subscription.canceled_at, tz=timezone.utc)
                if subscription.canceled_at
                else None
            ),
        )

        logger.info(
            f"Updated subscription {subscription.id} (status: {subscription.status})"
        )

    except Exception as e:
        logger.error(f"Failed to handle subscription updated: {e}")
        raise


async def handle_subscription_deleted(subscription, repo: SubscriptionRepository):
    """Handle subscription deletion/cancellation.

    Args:
        subscription: Stripe subscription object
        repo: Subscription repository
    """
    try:
        # Get user by Stripe customer ID
        user = await repo.get_user_by_stripe_customer(subscription.customer)
        if not user:
            logger.error(f"User not found for customer {subscription.customer}")
            return

        # Update subscription status to canceled
        price_id = subscription.items.data[0].price.id
        tier = get_tier_from_price_id(price_id)

        await repo.create_or_update_subscription(
            stripe_subscription_id=subscription.id,
            user_id=user["id"],
            stripe_price_id=price_id,
            status="canceled",
            tier=tier,
            current_period_start=datetime.fromtimestamp(
                subscription.current_period_start, tz=timezone.utc
            ),
            current_period_end=datetime.fromtimestamp(
                subscription.current_period_end, tz=timezone.utc
            ),
            cancel_at_period_end=True,
            canceled_at=datetime.now(tz=timezone.utc),
        )

        logger.info(f"Deleted subscription {subscription.id}")

    except Exception as e:
        logger.error(f"Failed to handle subscription deleted: {e}")
        raise


async def handle_payment_succeeded(invoice, repo: SubscriptionRepository):
    """Handle successful payment.

    Args:
        invoice: Stripe invoice object
        repo: Subscription repository
    """
    try:
        subscription_id = invoice.subscription
        if not subscription_id:
            logger.info("Invoice not related to subscription, skipping")
            return

        logger.info(
            f"Payment succeeded for subscription {subscription_id} "
            f"(amount: {invoice.amount_paid / 100} {invoice.currency.upper()})"
        )

        # Subscription status will be updated via subscription.updated webhook
        # No additional action needed here

    except Exception as e:
        logger.error(f"Failed to handle payment succeeded: {e}")
        raise


async def handle_payment_failed(invoice, repo: SubscriptionRepository):
    """Handle failed payment.

    Args:
        invoice: Stripe invoice object
        repo: Subscription repository
    """
    try:
        subscription_id = invoice.subscription
        if not subscription_id:
            logger.info("Invoice not related to subscription, skipping")
            return

        logger.warning(
            f"Payment failed for subscription {subscription_id} "
            f"(amount: {invoice.amount_due / 100} {invoice.currency.upper()})"
        )

        # Subscription status will be updated to 'past_due' via subscription.updated webhook
        # Could send notification to user here

    except Exception as e:
        logger.error(f"Failed to handle payment failed: {e}")
        raise
