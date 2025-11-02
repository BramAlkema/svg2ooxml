"""Stripe payment service for subscription management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import stripe

logger = logging.getLogger(__name__)


class StripeService:
    """Service for managing Stripe payments and subscriptions."""

    def __init__(self, api_key: str):
        """Initialize Stripe service with API key.

        Args:
            api_key: Stripe secret API key
        """
        stripe.api_key = api_key
        self.api_key = api_key
        logger.info("Stripe service initialized")

    async def create_customer(
        self,
        email: str,
        firebase_uid: str,
        name: Optional[str] = None,
    ) -> str:
        """Create a new Stripe customer.

        Args:
            email: Customer email address
            firebase_uid: Firebase UID for metadata
            name: Optional customer name

        Returns:
            Stripe customer ID

        Raises:
            stripe.error.StripeError: If customer creation fails
        """
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={"firebase_uid": firebase_uid},
            )
            logger.info(f"Created Stripe customer {customer.id} for user {firebase_uid}")
            return customer.id

        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            raise

    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> Dict[str, Any]:
        """Create a Stripe checkout session for subscription.

        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price ID for the subscription
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect if payment is canceled

        Returns:
            Dictionary with checkout_url and session_id

        Raises:
            stripe.error.StripeError: If session creation fails
        """
        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                allow_promotion_codes=True,
                subscription_data={
                    "trial_period_days": 0,  # No trial by default
                },
            )

            logger.info(f"Created checkout session {session.id} for customer {customer_id}")

            return {
                "checkout_url": session.url,
                "session_id": session.id,
            }

        except stripe.error.StripeError as e:
            logger.error(f"Failed to create checkout session: {e}")
            raise

    async def create_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> Dict[str, Any]:
        """Create a Stripe customer portal session.

        Args:
            customer_id: Stripe customer ID
            return_url: URL to return to after portal session

        Returns:
            Dictionary with portal_url

        Raises:
            stripe.error.StripeError: If portal session creation fails
        """
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )

            logger.info(f"Created portal session for customer {customer_id}")

            return {
                "portal_url": session.url,
            }

        except stripe.error.StripeError as e:
            logger.error(f"Failed to create portal session: {e}")
            raise

    async def get_subscription(
        self,
        subscription_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get subscription details from Stripe.

        Args:
            subscription_id: Stripe subscription ID

        Returns:
            Dictionary with subscription details or None if not found
        """
        try:
            sub = stripe.Subscription.retrieve(subscription_id)

            return {
                "id": sub.id,
                "status": sub.status,
                "current_period_start": datetime.fromtimestamp(
                    sub.current_period_start, tz=timezone.utc
                ),
                "current_period_end": datetime.fromtimestamp(
                    sub.current_period_end, tz=timezone.utc
                ),
                "cancel_at_period_end": sub.cancel_at_period_end,
                "canceled_at": (
                    datetime.fromtimestamp(sub.canceled_at, tz=timezone.utc)
                    if sub.canceled_at
                    else None
                ),
                "price_id": sub.items.data[0].price.id if sub.items.data else None,
            }

        except stripe.error.StripeError as e:
            logger.error(f"Failed to get subscription {subscription_id}: {e}")
            return None

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        webhook_secret: str,
    ) -> stripe.Event:
        """Verify and parse Stripe webhook event.

        Args:
            payload: Raw webhook payload
            signature: Stripe-Signature header value
            webhook_secret: Webhook endpoint secret

        Returns:
            Verified Stripe event

        Raises:
            stripe.error.SignatureVerificationError: If signature is invalid
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, webhook_secret
            )
            logger.info(f"Verified webhook event: {event.type}")
            return event

        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid webhook signature: {e}")
            raise

    async def cancel_subscription(
        self,
        subscription_id: str,
        immediately: bool = False,
    ) -> Dict[str, Any]:
        """Cancel a subscription.

        Args:
            subscription_id: Stripe subscription ID
            immediately: If True, cancel immediately; otherwise cancel at period end

        Returns:
            Updated subscription details

        Raises:
            stripe.error.StripeError: If cancellation fails
        """
        try:
            if immediately:
                sub = stripe.Subscription.delete(subscription_id)
            else:
                sub = stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True,
                )

            logger.info(
                f"Canceled subscription {subscription_id} "
                f"({'immediately' if immediately else 'at period end'})"
            )

            return {
                "id": sub.id,
                "status": sub.status,
                "cancel_at_period_end": sub.cancel_at_period_end,
            }

        except stripe.error.StripeError as e:
            logger.error(f"Failed to cancel subscription: {e}")
            raise
