"""Usage tracking operations for :class:`SubscriptionRepository`."""

from __future__ import annotations

import logging
from typing import Any

from firebase_admin import firestore

logger = logging.getLogger(__name__)


class SubscriptionRepoUsageMixin:
    """Mixin with usage lookup/increment helpers."""

    def get_usage(self, firebase_uid: str, month_year: str) -> dict[str, Any] | None:
        """Get usage for specific month."""

        try:
            doc_id = f"{firebase_uid}_{month_year}"
            doc = self.db.collection("usage").document(doc_id).get()

            if not doc.exists:
                return None

            return {"id": doc.id, **doc.to_dict()}

        except Exception as e:
            logger.error(f"Failed to get usage for {firebase_uid}/{month_year}: {e}")
            return None

    def increment_usage(self, firebase_uid: str, month_year: str) -> dict[str, Any]:
        """Increment usage count for current month using a Firestore transaction."""

        try:
            doc_id = f"{firebase_uid}_{month_year}"
            usage_ref = self.db.collection("usage").document(doc_id)

            @firestore.transactional
            def update_in_transaction(transaction, ref):
                snapshot = ref.get(transaction=transaction)

                if snapshot.exists:
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

            transaction = self.db.transaction()
            new_count = update_in_transaction(transaction, usage_ref)

            logger.info(
                f"Incremented usage for {firebase_uid}/{month_year} to {new_count}"
            )

            doc = usage_ref.get()
            return {"id": doc.id, **doc.to_dict()}

        except Exception as e:
            logger.error(f"Failed to increment usage: {e}")
            raise


__all__ = ["SubscriptionRepoUsageMixin"]
