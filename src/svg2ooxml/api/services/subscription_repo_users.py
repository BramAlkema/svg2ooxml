"""User record operations for :class:`SubscriptionRepository`."""

from __future__ import annotations

import logging
from typing import Any

from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

logger = logging.getLogger(__name__)


class SubscriptionRepoUsersMixin:
    """Mixin with user lookup/update helpers."""

    def get_user(self, firebase_uid: str) -> dict[str, Any] | None:
        """Get user by Firebase UID."""

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
        """Create or update user record."""

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

    def get_user_by_stripe_customer(self, stripe_customer_id: str) -> dict[str, Any] | None:
        """Find user by Stripe customer ID."""

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


__all__ = ["SubscriptionRepoUsersMixin"]
