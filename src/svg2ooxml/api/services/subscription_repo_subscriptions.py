"""Subscription record operations for :class:`SubscriptionRepository`."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

logger = logging.getLogger(__name__)


class SubscriptionRepoSubscriptionsMixin:
    """Mixin with subscription lookup/update helpers."""

    def get_active_subscription(self, firebase_uid: str) -> dict[str, Any] | None:
        """Get active subscription for user."""

        try:
            query = (
                self.db.collection("subscriptions")
                .where(filter=FieldFilter("userId", "==", firebase_uid))
                .where(filter=FieldFilter("status", "==", "active"))
                .limit(1)
            )

            docs = query.stream()

            for doc in docs:
                return {"id": doc.id, **doc.to_dict()}

            return None

        except Exception as e:
            logger.error(f"Failed to get active subscription for {firebase_uid}: {e}")
            return None

    def create_or_update_subscription(
        self,
        stripe_subscription_id: str,
        user_id: str,
        stripe_price_id: str,
        status: str,
        tier: str,
        current_period_start: datetime,
        current_period_end: datetime,
        cancel_at_period_end: bool = False,
        canceled_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Create or update subscription record."""

        try:
            sub_ref = self.db.collection("subscriptions").document(stripe_subscription_id)

            data = {
                "userId": user_id,
                "stripeSubscriptionId": stripe_subscription_id,
                "stripePriceId": stripe_price_id,
                "status": status,
                "tier": tier,
                "currentPeriodStart": current_period_start,
                "currentPeriodEnd": current_period_end,
                "cancelAtPeriodEnd": cancel_at_period_end,
                "canceledAt": canceled_at,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }

            doc = sub_ref.get()
            if not doc.exists:
                data["createdAt"] = firestore.SERVER_TIMESTAMP

            sub_ref.set(data, merge=True)
            logger.info(f"Created/updated subscription {stripe_subscription_id}")

            return {"id": stripe_subscription_id, **data}

        except Exception as e:
            logger.error(f"Failed to create/update subscription: {e}")
            raise

    def get_subscription(self, stripe_subscription_id: str) -> dict[str, Any] | None:
        """Get subscription by Stripe ID."""

        try:
            doc = (
                self.db.collection("subscriptions")
                .document(stripe_subscription_id)
                .get()
            )

            if not doc.exists:
                return None

            return {"id": doc.id, **doc.to_dict()}

        except Exception as e:
            logger.error(f"Failed to get subscription {stripe_subscription_id}: {e}")
            return None


__all__ = ["SubscriptionRepoSubscriptionsMixin"]
