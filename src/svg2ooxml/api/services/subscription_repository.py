"""Firestore repository for subscription and usage data."""

from __future__ import annotations

import logging

from firebase_admin import firestore

from .subscription_repo_subscriptions import SubscriptionRepoSubscriptionsMixin
from .subscription_repo_usage import SubscriptionRepoUsageMixin
from .subscription_repo_users import SubscriptionRepoUsersMixin

logger = logging.getLogger(__name__)


class SubscriptionRepository(
    SubscriptionRepoUsersMixin,
    SubscriptionRepoSubscriptionsMixin,
    SubscriptionRepoUsageMixin,
):
    """Repository for managing subscription data in Firestore."""

    def __init__(self):
        """Initialize repository with Firestore client."""

        self.db = firestore.client()
        logger.info("Subscription repository initialized")


__all__ = ["SubscriptionRepository"]
