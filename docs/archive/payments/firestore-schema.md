# Firestore Database Schema

## Overview
Using Cloud Firestore (not Realtime Database) for subscription and usage data.

## Collections

### `/users`
Stores user profile and Stripe customer information.

**Document ID**: Firebase UID (from Firebase Auth)

**Fields**:
```javascript
{
  email: string,                    // User's email
  stripeCustomerId: string | null,  // Stripe customer ID
  createdAt: timestamp,              // Account creation time
  updatedAt: timestamp               // Last update time
}
```

**Example**:
```javascript
/users/abc123xyz {
  email: "user@example.com",
  stripeCustomerId: "cus_ABC123",
  createdAt: 2024-11-02T10:00:00Z,
  updatedAt: 2024-11-02T10:00:00Z
}
```

**Indexes**: None needed (queries by document ID)

---

### `/subscriptions`
Stores active and historical subscriptions.

**Document ID**: Stripe subscription ID

**Fields**:
```javascript
{
  userId: string,                    // Firebase UID (reference to /users)
  stripeSubscriptionId: string,      // Stripe subscription ID
  stripePriceId: string,             // Stripe price ID
  status: string,                    // "active" | "canceled" | "past_due" | "unpaid" | "incomplete"
  tier: string,                      // "free" | "pro" | "enterprise"
  currentPeriodStart: timestamp,     // Billing period start
  currentPeriodEnd: timestamp,       // Billing period end
  cancelAtPeriodEnd: boolean,        // Will cancel at end of period
  canceledAt: timestamp | null,      // When subscription was canceled
  createdAt: timestamp,              // Subscription creation time
  updatedAt: timestamp               // Last update time
}
```

**Example**:
```javascript
/subscriptions/sub_ABC123 {
  userId: "abc123xyz",
  stripeSubscriptionId: "sub_ABC123",
  stripePriceId: "price_pro_monthly",
  status: "active",
  tier: "pro",
  currentPeriodStart: 2024-11-01T00:00:00Z,
  currentPeriodEnd: 2024-12-01T00:00:00Z,
  cancelAtPeriodEnd: false,
  canceledAt: null,
  createdAt: 2024-11-01T00:00:00Z,
  updatedAt: 2024-11-01T00:00:00Z
}
```

**Indexes**:
- Composite: `userId` (Ascending) + `status` (Ascending)
- Single: `status` (Ascending)

---

### `/usage`
Tracks monthly export usage per user.

**Document ID**: `{userId}_{monthYear}` (e.g., `abc123xyz_2024-11`)

**Fields**:
```javascript
{
  userId: string,                    // Firebase UID
  monthYear: string,                 // Format: "YYYY-MM"
  exportCount: number,               // Number of exports this month
  lastExportAt: timestamp | null,    // Last export timestamp
  createdAt: timestamp,              // First export this month
  updatedAt: timestamp               // Last update time
}
```

**Example**:
```javascript
/usage/abc123xyz_2024-11 {
  userId: "abc123xyz",
  monthYear: "2024-11",
  exportCount: 3,
  lastExportAt: 2024-11-02T15:30:00Z,
  createdAt: 2024-11-01T08:00:00Z,
  updatedAt: 2024-11-02T15:30:00Z
}
```

**Indexes**:
- Single: `userId` (Ascending)
- Single: `monthYear` (Ascending)

---

## Usage Patterns

### Check Subscription Status
```javascript
// Get user
const userDoc = await db.collection('users').doc(firebaseUid).get();

// Get active subscription
const subsSnapshot = await db.collection('subscriptions')
  .where('userId', '==', firebaseUid)
  .where('status', '==', 'active')
  .limit(1)
  .get();

// Get current month usage
const monthYear = new Date().toISOString().slice(0, 7); // "2024-11"
const usageDoc = await db.collection('usage').doc(`${firebaseUid}_${monthYear}`).get();
```

### Increment Usage
```javascript
const monthYear = new Date().toISOString().slice(0, 7);
const usageRef = db.collection('usage').doc(`${firebaseUid}_${monthYear}`);

await db.runTransaction(async (transaction) => {
  const doc = await transaction.get(usageRef);

  if (doc.exists) {
    transaction.update(usageRef, {
      exportCount: admin.firestore.FieldValue.increment(1),
      lastExportAt: admin.firestore.FieldValue.serverTimestamp(),
      updatedAt: admin.firestore.FieldValue.serverTimestamp()
    });
  } else {
    transaction.set(usageRef, {
      userId: firebaseUid,
      monthYear: monthYear,
      exportCount: 1,
      lastExportAt: admin.firestore.FieldValue.serverTimestamp(),
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      updatedAt: admin.firestore.FieldValue.serverTimestamp()
    });
  }
});
```

### Webhook: Create/Update Subscription
```javascript
// From Stripe webhook event
const subscription = event.data.object;

await db.collection('subscriptions').doc(subscription.id).set({
  userId: userFirebaseUid,
  stripeSubscriptionId: subscription.id,
  stripePriceId: subscription.items.data[0].price.id,
  status: subscription.status,
  tier: getTierFromPriceId(subscription.items.data[0].price.id),
  currentPeriodStart: new Date(subscription.current_period_start * 1000),
  currentPeriodEnd: new Date(subscription.current_period_end * 1000),
  cancelAtPeriodEnd: subscription.cancel_at_period_end,
  canceledAt: subscription.canceled_at ? new Date(subscription.canceled_at * 1000) : null,
  createdAt: admin.firestore.FieldValue.serverTimestamp(),
  updatedAt: admin.firestore.FieldValue.serverTimestamp()
}, { merge: true });
```

## Security Rules

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Users collection - users can only read their own data
    match /users/{userId} {
      allow read: if request.auth != null && request.auth.uid == userId;
      allow write: if false; // Only backend can write
    }

    // Subscriptions - users can only read their own
    match /subscriptions/{subscriptionId} {
      allow read: if request.auth != null &&
                     resource.data.userId == request.auth.uid;
      allow write: if false; // Only backend can write
    }

    // Usage - users can only read their own
    match /usage/{usageId} {
      allow read: if request.auth != null &&
                     resource.data.userId == request.auth.uid;
      allow write: if false; // Only backend can write
    }
  }
}
```

## Advantages Over SQL

1. **No Connection Management**: Firestore is HTTP-based, no connection pools needed
2. **Auto-scaling**: Handles traffic spikes automatically
3. **Already Integrated**: Firebase Admin SDK already installed
4. **Generous Free Tier**: 50K reads, 20K writes, 1GB storage per day
5. **Real-time Capabilities**: Can add real-time listeners if needed
6. **Offline Support**: Works offline in client SDKs
7. **Built-in Security**: Firestore Security Rules

## Cost Estimate

Based on Firestore pricing (free tier: 50K reads, 20K writes/day):

**Typical Usage** (100 active users, 50 exports/day):
- Reads: ~150/day (3 per export: user + subscription + usage)
- Writes: ~50/day (1 per export)
- **Cost**: $0/month (within free tier)

**Heavy Usage** (1000 users, 500 exports/day):
- Reads: ~1,500/day
- Writes: ~500/day
- **Cost**: $0/month (still within free tier)

**At Scale** (10K users, 5K exports/day):
- Reads: ~15K/day (within free tier)
- Writes: ~5K/day (within free tier)
- **Cost**: $0/month

Even at significant scale, Firestore costs are minimal compared to Cloud SQL ($10-50/month minimum).

## Migration Path

If we ever need to migrate to SQL:
1. Export Firestore data using `gcloud firestore export`
2. Transform to SQL format
3. Import to Cloud SQL
4. Update backend to use SQL adapter

For now, Firestore is the perfect choice for this use case!
