# PR Predictor API documentation

Base URL: `http://127.0.0.1:8000`

The service returns JSON unless an endpoint says it returns HTML. Request and response property names use **camelCase**. Protected endpoints require:

```http
Authorization: Bearer <accessToken>
```

A normal error has this shape:

```json
{ "detail": "safe human-readable message" }
```

Common status codes are `400` invalid input, `401` missing/invalid token or bad login, `403` insufficient role, `404` missing record, `409` duplicate account data, `422` request validation failure, and `429` monthly quota reached.

## Public API

### `GET /`

No authentication or input.

Success `200`:

```json
{
  "message": "PR Predictor API is running",
  "docs": "/docs",
  "admin": "/admin/"
}
```

### `GET /health`

No authentication or input.

Success `200`:

```json
{ "status": "ok" }
```

### `POST /register`

No authentication. Creates a normal `USER` account and signs the user in immediately. The request body is:

```json
{
  "username": "sam",
  "email": "sam@example.com",
  "password": "pass1234",
  "fullName": "Sam Student",
  "githubProfileUrl": "https://github.com/sam"
}
```

`username` is 3–80 characters, `email` is 5–255 characters, `password` is 4–128 characters, and `githubProfileUrl` is optional. `role` is not accepted from registration.

Success `201` returns the login response shown under [`POST /login`](#post-login). Duplicate username/email returns `409`.

### `POST /login`

No authentication. The `username` value accepts either the username or account email.

Input:

```json
{ "username": "sam", "password": "pass1234" }
```

Success `200`:

```json
{
  "accessToken": "signed-token",
  "tokenType": "bearer",
  "user": {
    "userId": "uuid",
    "username": "sam",
    "email": "sam@example.com",
    "fullName": "Sam Student",
    "role": "USER",
    "githubProfileUrl": null,
    "createdAt": "2026-09-30T12:00:00"
  }
}
```

Wrong credentials return `401`.

## Authenticated user API

### `GET /me` and `GET /profile`

Authentication: bearer token. No body or query parameters.

Both paths return the same current-user object with `200`:

```json
{
  "userId": "uuid",
  "username": "sam",
  "email": "sam@example.com",
  "fullName": "Sam Student",
  "role": "USER",
  "githubProfileUrl": null,
  "createdAt": "2026-09-30T12:00:00"
}
```

### `PATCH /profile`

Authentication: bearer token. All fields are optional; only included fields are changed.

Input:

```json
{
  "fullName": "Sam Student Updated",
  "email": "new-email@example.com",
  "githubProfileUrl": "https://github.com/sam"
}
```

Success `200`: the updated user object from [`GET /me`](#get-me-and-get-profile). A duplicate email returns `409`.

### `GET /settings`

Authentication: bearer token. No input.

Success `200`:

```json
{
  "themeMode": "LIGHT",
  "notificationsEnabled": true,
  "defaultPredictionType": "BOTH",
  "defaultInputMode": "GITHUB_URL"
}
```

### `PATCH /settings`

Authentication: bearer token. All fields are optional.

Input:

```json
{
  "themeMode": "DARK",
  "notificationsEnabled": false,
  "defaultPredictionType": "MERGE_PROBABILITY",
  "defaultInputMode": "MANUAL_FEATURES"
}
```

Allowed values are `LIGHT`/`DARK`, `MERGE_PROBABILITY`/`PR_QUALITY`/`BOTH`, and `GITHUB_URL`/`MANUAL_FEATURES`.

Success `200`: the settings object from [`GET /settings`](#get-settings). Invalid values return `400`.

### `GET /models`

Authentication: bearer token. Optional query parameter: `predictionType` (`MERGE_PROBABILITY`, `PR_QUALITY`, or `BOTH`).

Example: `GET /models?predictionType=BOTH`

Success `200`:

```json
[
  {
    "modelId": "uuid",
    "code": "merge-probability-v1",
    "name": "PR Predictor Demo",
    "taskType": "BOTH",
    "version": "1.0",
    "provider": "local",
    "description": "A deterministic demo model based on submitted features."
  }
]
```

Only active models are returned. The default seeded model code is `merge-probability-v1`.

### `GET /subscription`

Authentication: bearer token. No input.

Success `200`:

```json
{
  "subscriptionId": "uuid",
  "status": "ACTIVE",
  "startedAt": "2026-09-30T12:00:00",
  "plan": {
    "code": "FREE",
    "name": "Free",
    "monthlyPredictionLimit": 5,
    "description": "5 predictions each month"
  }
}
```

### `POST /subscription`

Authentication: bearer token. This is a local demo plan switch; it does not charge money.

Input:

```json
{ "planCode": "PREMIUM" }
```

`planCode` is `FREE` or `PREMIUM`.

Success `200`: the subscription object from [`GET /subscription`](#get-subscription). Unknown plans return `404`.

## Prediction API

### `POST /predict`

Authentication: bearer token. The request is processed synchronously, persisted, and returned as one completed prediction. Free accounts have five predictions per calendar month; Premium accounts are unlimited.

Use one of these input shapes.

GitHub pull request input:

```json
{
  "inputType": "GITHUB_URL",
  "predictionType": "BOTH",
  "modelId": "merge-probability-v1",
  "pullRequestUrl": "https://github.com/openai/example/pull/12"
}
```

Manual feature input:

```json
{
  "inputType": "MANUAL_FEATURES",
  "predictionType": "MERGE_PROBABILITY",
  "modelId": "merge-probability-v1",
  "features": {
    "changedFiles": 12,
    "additions": 150,
    "deletions": 25,
    "testsAdded": true
  }
}
```

`inputType` is `GITHUB_URL` or `MANUAL_FEATURES`. `predictionType` is `MERGE_PROBABILITY`, `PR_QUALITY`, or `BOTH`. `modelId` is optional and accepts a model UUID or model code. GitHub URLs must match `https://github.com/{owner}/{repo}/pull/{number}`. Manual `features` must contain at least one value.

Success `200`:

```json
{
  "predictionId": "uuid",
  "status": "COMPLETED",
  "predictionType": "BOTH",
  "createdAt": "2026-09-30T12:00:00",
  "completedAt": "2026-09-30T12:00:01",
  "modelVersion": "1.0",
  "model": {
    "modelId": "uuid",
    "code": "merge-probability-v1",
    "name": "PR Predictor Demo",
    "taskType": "BOTH",
    "version": "1.0",
    "provider": "local",
    "description": "A deterministic demo model based on submitted features."
  },
  "repository": {
    "owner": "openai",
    "name": "example",
    "url": "https://github.com/openai/example"
  },
  "pullRequest": {
    "number": 12,
    "url": "https://github.com/openai/example/pull/12",
    "title": "Pull request #12",
    "state": "OPEN",
    "authorLogin": "openai"
  },
  "mergeProbability": 78.5,
  "qualityScore": 81.2,
  "qualityLabel": "Excellent",
  "recommendation": "Looks ready for review. Keep the existing tests and ask a reviewer to verify the edge cases.",
  "factors": [
    {
      "name": "Change size",
      "description": "4 changed files and 188 line changes were considered.",
      "impact": "POSITIVE",
      "order": 0
    }
  ]
}
```

For manual predictions, `repository` and `pullRequest` are `null`. For `MERGE_PROBABILITY`, `qualityScore` is `null`; for `PR_QUALITY`, `mergeProbability` is `null`. A missing model returns `404`; quota exhaustion returns `429`.

### `GET /history` and `GET /predictions`

Authentication: bearer token. These are aliases and return the same list of the current user's newest predictions.

Optional query parameters:

- `search`: matches stored pull-request URL or title.
- `limit`: number of records, default `20`, minimum `1`, maximum `100`.

Example: `GET /history?search=example&limit=20`

Success `200`: an array of prediction objects using the response shape from [`POST /predict`](#post-predict).

```json
[
  {
    "predictionId": "uuid",
    "status": "COMPLETED",
    "predictionType": "BOTH",
    "mergeProbability": 78.5,
    "qualityScore": 81.2,
    "qualityLabel": "Excellent",
    "repository": { "owner": "openai", "name": "example", "url": "https://github.com/openai/example" },
    "pullRequest": { "number": 12, "url": "https://github.com/openai/example/pull/12", "title": "Pull request #12", "state": "OPEN", "authorLogin": "openai" }
  }
]
```

### `GET /predictions/{predictionId}`

Authentication: bearer token. Path input: `predictionId` (UUID string).

Success `200`: one prediction object using the response shape from [`POST /predict`](#post-predict). A prediction owned by another user or an unknown ID returns `404`.

### `GET /dashboard`

Authentication: bearer token. No input.

Success `200`:

```json
{
  "totalPredictions": 12,
  "averageMergeProbability": 72.4,
  "usage": { "used": 2, "limit": 5 },
  "subscription": {
    "subscriptionId": "uuid",
    "status": "ACTIVE",
    "startedAt": "2026-09-30T12:00:00",
    "plan": { "code": "FREE", "name": "Free", "monthlyPredictionLimit": 5, "description": "5 predictions each month" }
  },
  "recentPredictions": []
}
```

## Private admin API

These endpoints are for the simple browser console at `GET /admin/`. They require a bearer token belonging to a user whose `role` is `ADMIN`; ordinary users receive `403`.

### `GET /admin/`

No API input. Returns the admin HTML page (`200`) with its CSS and JavaScript assets. The page signs in through [`POST /login`](#post-login) and then calls the private JSON endpoints below.

### `GET /admin/api/stats`

Authentication: admin bearer token. No input.

Success `200`:

```json
{ "users": 4, "predictions": 18, "models": 1, "plans": 2 }
```

### `GET /admin/api/users`

Authentication: admin bearer token. No input.

Success `200`: an array of public user objects (the same fields returned by [`GET /me`](#get-me-and-get-profile)); password hashes are never returned.

```json
[
  {
    "userId": "uuid",
    "username": "sam",
    "email": "sam@example.com",
    "fullName": "Sam Student",
    "role": "USER",
    "githubProfileUrl": null,
    "createdAt": "2026-09-30T12:00:00"
  }
]
```

### `GET /admin/api/models`

Authentication: admin bearer token. No input.

Success `200`: all model catalog records, including inactive records retained for prediction history.

```json
[
  {
    "modelId": "uuid",
    "code": "merge-probability-v1",
    "name": "PR Predictor Demo",
    "taskType": "BOTH",
    "version": "1.0",
    "provider": "local",
    "description": "A deterministic demo model based on submitted features.",
    "active": true,
    "createdAt": "2026-09-30T12:00:00",
    "retiredAt": null
  }
]
```

### `POST /admin/api/models`

Authentication: admin bearer token. Creates a model catalog record.

Input:

```json
{
  "code": "review-model-v2",
  "name": "Review Model v2",
  "taskType": "BOTH",
  "version": "2.0",
  "provider": "local",
  "description": "A short description for the model selector.",
  "active": true
}
```

`taskType` must be `MERGE_PROBABILITY`, `PR_QUALITY`, or `BOTH`. `code`, `name`, and `version` are required. `provider`, `description`, and `active` are optional; `active` defaults to `true`.

Success `201`: the created model object using the [`GET /admin/api/models`](#get-adminapimodels) shape. A duplicate code returns `409`.

### `PATCH /admin/api/models/{modelId}`

Authentication: admin bearer token. Path input: `modelId` (UUID string). All body fields are optional and only included fields change.

Input:

```json
{
  "name": "Review Model v2.1",
  "taskType": "PR_QUALITY",
  "version": "2.1",
  "provider": "local",
  "description": "Updated description.",
  "active": true
}
```

The `code` field may also be changed, but it must remain unique. Success `200`: the updated model object. Unknown IDs return `404`, duplicate codes return `409`, and invalid task types return `400`.

### `DELETE /admin/api/models/{modelId}`

Authentication: admin bearer token. Path input: `modelId` (UUID string). No body.

This is a soft delete: the model is marked inactive and receives a retirement timestamp, while historical predictions continue to reference it. Inactive models are not returned by the public [`GET /models`](#get-models) endpoint.

Success `200`:

```json
{
  "message": "Model deactivated",
  "model": {
    "modelId": "uuid",
    "code": "review-model-v2",
    "name": "Review Model v2",
    "taskType": "BOTH",
    "version": "2.0",
    "provider": "local",
    "description": "A short description for the model selector.",
    "active": false,
    "createdAt": "2026-09-30T12:00:00",
    "retiredAt": "2026-10-01T12:00:00"
  }
}
```

An inactive model can be reactivated with `PATCH /admin/api/models/{modelId}` and `{ "active": true }`.

### `PATCH /admin/api/users/{userId}/role`

Authentication: admin bearer token. Path input: `userId` (UUID string).

Request body:

```json
{ "role": "ADMIN" }
```

`role` must be `USER` or `ADMIN`.

Success `200`: the updated public user object. Unknown user returns `404`; invalid role returns `400`.

### `GET /admin/api/predictions`

Authentication: admin bearer token. No input.

Success `200`: the latest 100 prediction summaries:

```json
[
  {
    "predictionId": "uuid",
    "username": "sam",
    "status": "COMPLETED",
    "predictionType": "BOTH",
    "createdAt": "2026-09-30T12:00:00"
  }
]
```
