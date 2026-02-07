"""Firestore repository for subscription and usage data."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

logger = logging.getLogger(__name__)


class SubscriptionRepository:
    """Repository for managing subscription data in Firestore."""

    def __init__(self):
        """Initialize repository with Firestore client."""
        self.db = firestore.client()
        logger.info("Subscription repository initialized")

    # ============================================================================
    # Users
    # ============================================================================

    def get_user(self, firebase_uid: str) -> dict[str, Any] | None:
        """Get user by Firebase UID.

        Args:
            firebase_uid: Firebase user ID

        Returns:
            User data or None if not found
        """
        try:
            doc = self.db.collection("users").document(firebase_uid).get()

            if not doc.exists:
                return None

            return {"id": doc.id, **doc.to_dict()}

        except Exception as e:
            logger.error(f"Failed to get user {firebase_uid}: {e}")
            return None

    def create_or_update_user(
        self,
        firebase_uid: str,
        email: str,
        stripe_customer_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or update user record.

        Args:
            firebase_uid: Firebase user ID
            email: User email
            stripe_customer_id: Optional Stripe customer ID

        Returns:
            Updated user data
        """
        try:
            user_ref = self.db.collection("users").document(firebase_uid)
            doc = user_ref.get()

            data = {
                "email": email,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }

            if stripe_customer_id:
                data["stripeCustomerId"] = stripe_customer_id

            if not doc.exists:
                data["createdAt"] = firestore.SERVER_TIMESTAMP
                user_ref.set(data)
                logger.info(f"Created user {firebase_uid}")
            else:
                user_ref.update(data)
                logger.info(f"Updated user {firebase_uid}")

            return {"id": firebase_uid, **data}

        except Exception as e:
            logger.error(f"Failed to create/update user: {e}")
            raise

    # ============================================================================
    # Subscriptions
    # ============================================================================

    def get_active_subscription(
        self, firebase_uid: str
    ) -> dict[str, Any] | None:
        """Get active subscription for user.

        Args:
            firebase_uid: Firebase user ID

        Returns:
            Active subscription data or None
        """
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
        """Create or update subscription record.

        Args:
            stripe_subscription_id: Stripe subscription ID
            user_id: Firebase user ID
            stripe_price_id: Stripe price ID
            status: Subscription status
            tier: Subscription tier (free/pro/enterprise)
            current_period_start: Billing period start
            current_period_end: Billing period end
            cancel_at_period_end: Will cancel at period end
            canceled_at: Cancellation timestamp

        Returns:
            Updated subscription data
        """
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

    def get_subscription(
        self, stripe_subscription_id: str
    ) -> dict[str, Any] | None:
        """Get subscription by Stripe ID.

        Args:
            stripe_subscription_id: Stripe subscription ID

        Returns:
            Subscription data or None
        """
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

    # ============================================================================
    # Usage Tracking
    # ============================================================================

    def get_usage(
        self, firebase_uid: str, month_year: str
    ) -> dict[str, Any] | None:
        """Get usage for specific month.

        Args:
            firebase_uid: Firebase user ID
            month_year: Month in YYYY-MM format

        Returns:
            Usage data or None
        """
        try:
            doc_id = f"{firebase_uid}_{month_year}"
            doc = self.db.collection("usage").document(doc_id).get()

            if not doc.exists:
                return None

            return {"id": doc.id, **doc.to_dict()}

        except Exception as e:
            logger.error(f"Failed to get usage for {firebase_uid}/{month_year}: {e}")
            return None

    def increment_usage(
        self, firebase_uid: str, month_year: str
    ) -> dict[str, Any]:
        """Increment usage count for current month.

        Uses Firestore transaction to ensure atomic increment.

        Args:
            firebase_uid: Firebase user ID
            month_year: Month in YYYY-MM format

        Returns:
            Updated usage data
        """
        try:
            doc_id = f"{firebase_uid}_{month_year}"
            usage_ref = self.db.collection("usage").document(doc_id)

            @firestore.transactional
            def update_in_transaction(transaction, ref):
                snapshot = ref.get(transaction=transaction)

                if snapshot.exists:
                    # Increment existing counter
                    transaction.update(
                        ref,
                        {
                            "exportCount": firestore.Increment(1),
                            "lastExportAt": firestore.SERVER_TIMESTAMP,
                            "updatedAt": firestore.SERVER_TIMESTAMP,
                        },
                    )
                    current_count = snapshot.get("exportCount")
                    new_count = current_count + 1
                else:
                    # Create new usage record
                    transaction.set(
                        ref,
                        {
                            "userId": firebase_uid,
                            "monthYear": month_year,
                            "exportCount": 1,
                            "lastExportAt": firestore.SERVER_TIMESTAMP,
                            "createdAt": firestore.SERVER_TIMESTAMP,
                            "updatedAt": firestore.SERVER_TIMESTAMP,
                        },
                    )
                    new_count = 1

                return new_count

            # Execute transaction
            transaction = self.db.transaction()
            new_count = update_in_transaction(transaction, usage_ref)

            logger.info(
                f"Incremented usage for {firebase_uid}/{month_year} to {new_count}"
            )

            # Get updated document
            doc = usage_ref.get()
            return {"id": doc.id, **doc.to_dict()}

        except Exception as e:
            logger.error(f"Failed to increment usage: {e}")
            raise

    def get_user_by_stripe_customer(
        self, stripe_customer_id: str
    ) -> dict[str, Any] | None:
        """Find user by Stripe customer ID.

        Args:
            stripe_customer_id: Stripe customer ID

        Returns:
            User data or None
        """
        try:
            query = self.db.collection("users").where(
                filter=FieldFilter("stripeCustomerId", "==", stripe_customer_id)
            ).limit(1)

            docs = query.stream()

            for doc in docs:
                return {"id": doc.id, **doc.to_dict()}

            return None

        except Exception as e:
            logger.error(
                f"Failed to find user by Stripe customer {stripe_customer_id}: {e}"
            )
            return None
