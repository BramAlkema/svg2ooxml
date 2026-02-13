"""Webhook handlers for external services."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

import stripe
from fastapi import APIRouter, HTTPException, Request
from firebase_admin import firestore

from ..services.stripe_service import StripeService
from ..services.subscription_repository import SubscriptionRepository
from .webhooks_handlers import (
    handle_payment_failed,
    handle_payment_succeeded,
    handle_subscription_created,
    handle_subscription_deleted,
    handle_subscription_updated,
)

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
            "expires_at": datetime.now(UTC).timestamp() + 86400,  # 24 hours
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
        raise HTTPException(status_code=400, detail="Invalid signature") from e

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
