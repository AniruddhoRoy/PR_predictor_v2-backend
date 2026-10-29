# PR Predictor API documentation

Base URL: `http://127.0.0.1:8000`

The prediction API needs one thing from the caller: a GitHub pull request URL. The server sends the URL to the hosted Gemini analyzer, saves its response, charges credits, and returns its scores and analysis.

This reference follows `app.py`, `schemas.py`, and `analysis_api.py`. It includes request fields, response examples, authentication, and errors for every application route.

## Contents

- [Basics and errors](#basics-and-errors)
- [Public routes](#public-routes)
- [Profile and settings](#profile-and-settings)
- [Models, plans, and credits](#models-plans-and-credits)
- [Predictions and history](#predictions-and-history)
- [Private admin routes](#private-admin-routes)
- [Browser pages](#browser-pages)
- [Python prediction helper](#python-prediction-helper)
- [Client example](#client-example)

## Basics and errors

Send bodies with `Content-Type: application/json`. Responses are JSON except browser pages and assets. Most routes use camelCase fields as shown; prediction success responses preserve the analyzer's original fields (including snake_case). Pydantic request models also accept their snake_case Python field names. Extra Pydantic request fields are ignored, not applied to database records, with one exception: `POST /predict` and `POST /predict-dev` reject unknown fields (see [Predictions and history](#predictions-and-history)).

| Authentication label | Required header                       | Access                                       |
| -------------------- | ------------------------------------- | -------------------------------------------- |
| Public               | None                                  | Anyone                                       |
| User                 | `Authorization: Bearer <accessToken>` | Signed-in users, including admins            |
| Admin                | `Authorization: Bearer <accessToken>` | Account whose current database role is ADMIN |

Get accessToken from registration or login. Treat it as an opaque string. Default expiry is 12 hours, configurable through TOKEN_TTL_SECONDS. There is no refresh-token or logout route; sign in again after expiry and remove the stored token on client logout.

Examples use placeholders such as `<userId>` for generated UUID strings. Replace path placeholders with IDs returned by the API. Timestamps and scores are illustrative. Current timestamps are UTC ISO strings without a timezone suffix. Scores are percentages from 0 to 100. Arrays have no `data` wrapper.

For PATCH, omit unchanged fields. Optional does not mean every field safely accepts null; use null only where explicitly described below.

Application errors have a string detail:

```json
{
  "detail": "Not enough credits for this model"
}
```

Validation errors normally have an array detail, for example a missing login password:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": [
        "body",
        "password"
      ],
      "msg": "Field required",
      "input": {
        "username": "sam"
      }
    }
  ]
}
```

Exact validation fields can vary with FastAPI/Pydantic versions. Handle both detail shapes.

| Status | Meaning                                                                                                                         |
| ------ | ------------------------------------------------------------------------------------------------------------------------------- |
| 200    | Successful read/update/prediction/deactivation                                                                                  |
| 201    | Account/model/plan created                                                                                                      |
| 400    | Unsupported value, invalid PR URL or prediction type, or invalid operation                                                      |
| 401    | Missing/invalid/expired token, deleted account, or incorrect login                                                              |
| 403    | Admin access required, or selected prediction model inaccessible/incompatible                                                   |
| 404    | Record, model, plan, or GitHub PR/repository not found                                                                          |
| 409    | Duplicate account/code or subscription changed during analysis                                                                                     |
| 422 | Missing/invalid input or the analyzer rejected the request/PR URL |
| 429 | Not enough plan credits |
| 502 | Analysis service connection error or invalid response |
| 503 | Missing service token, service configuration/quota issue, or service unavailable |
| 504 | GitHub, Gemini, or the analysis service timed out |

Every User/Admin route can return 401. Every Admin route can also return 403. These shared errors are not repeated for each endpoint. Unhandled failures may return 500 without the JSON shape above.

## Public routes

### `GET /`

Authentication: **Public**.

No path or query parameters. Returns service links.

**Request body:** none.

**Response 200:**

```json
{
  "message": "PR Predictor API is running",
  "docs": "/docs",
  "admin": "/admin/"
}
```

### `GET /health`

Authentication: **Public**.

No path or query parameters. Checks service liveness, not database connectivity or model readiness.

**Request body:** none.

**Response 200:**

```json
{
  "status": "ok"
}
```

### `POST /register`

Authentication: **Public**.

Identity fields are trimmed before validation: username must have 3-80 characters, email 5-255, and fullName 1-150. Blank or oversized values return 422. Password whitespace is preserved.

Creates a USER, default settings, and a FREE subscription when the active FREE plan exists. Signs the user in immediately.

| Field            | Type           | Required | Rules                                                           |
| ---------------- | -------------- | -------- | --------------------------------------------------------------- |
| username         | string         | Yes      | 3–80 characters; trimmed/lowercased                             |
| email            | string         | Yes      | 5–255 characters; trimmed/lowercased; no email-format validator |
| password         | string         | Yes      | 4–128 characters                                                |
| fullName         | string         | Yes      | 1–150 characters before trimming                                |
| githubProfileUrl | string or null | No       | Default null; no URL-format validator                           |

Registration cannot grant an admin role. Duplicate username/email returns 409: `Username or email is already registered`. Password hashes are never returned.

**Request body:**

```json
{
  "username": "sam",
  "email": "sam@example.com",
  "password": "pass1234",
  "fullName": "Sam Student",
  "githubProfileUrl": "https://github.com/sam"
}
```

**Response 201:**

```json
{
  "accessToken": "<accessToken>",
  "tokenType": "bearer",
  "user": {
    "userId": "<userId>",
    "username": "sam",
    "email": "sam@example.com",
    "fullName": "Sam Student",
    "role": "USER",
    "githubProfileUrl": "https://github.com/sam",
    "createdAt": "2026-10-04T12:00:00"
  }
}
```

### `POST /login`

Authentication: **Public**.

Required fields: username and password, both strings. username accepts a username or email and is trimmed/lowercased. Incorrect credentials return 401: `Incorrect username or password`.

**Request body:**

```json
{
  "username": "sam",
  "password": "pass1234"
}
```

**Response 200:**

```json
{
  "accessToken": "<accessToken>",
  "tokenType": "bearer",
  "user": {
    "userId": "<userId>",
    "username": "sam",
    "email": "sam@example.com",
    "fullName": "Sam Student",
    "role": "USER",
    "githubProfileUrl": "https://github.com/sam",
    "createdAt": "2026-10-04T12:00:00"
  }
}
```

Use the returned token on protected routes:

```http
Authorization: Bearer <accessToken>
```

## Profile and settings

### `GET /me`

Authentication: **User**.

No path/query parameters. Current public account information. `GET /profile` is an alias with the same response.

**Request body:** none.

**Response 200:**

```json
{
  "userId": "<userId>",
  "username": "sam",
  "email": "sam@example.com",
  "fullName": "Sam Student",
  "role": "USER",
  "githubProfileUrl": "https://github.com/sam",
  "createdAt": "2026-10-04T12:00:00"
}
```

### `PATCH /profile`

Authentication: **User**.

All fields are optional: fullName (1-150 characters after trimming), email (5-255 characters after trimming), githubProfileUrl (string or null). Blank, oversized, or null fullName/email values return 422. Null clears githubProfileUrl. Send a string for email; explicit null returns 422 and leaves the profile unchanged. Duplicate email returns 409: `Email is already registered`. Email is trimmed/lowercased, fullName is trimmed. This route cannot change username, password, or role.

**Request body:**

```json
{
  "fullName": "Sam Student Updated",
  "email": "sam.updated@example.com",
  "githubProfileUrl": null
}
```

**Response 200:**

```json
{
  "userId": "<userId>",
  "username": "sam",
  "email": "sam.updated@example.com",
  "fullName": "Sam Student Updated",
  "role": "USER",
  "githubProfileUrl": null,
  "createdAt": "2026-10-04T12:00:00"
}
```

### `POST /change-password`

Authentication: **User** (including admins).

Changes the signed-in account's password after checking its current password. No path or query parameters. Passwords are used exactly as sent, without trimming, and the new password is stored as a hash. Existing bearer tokens remain valid until their usual expiry; this route does not return a new token.

| Field           | Type   | Required | Rules            |
| --------------- | ------ | -------- | ---------------- |
| currentPassword | string | Yes      | 1–128 characters |
| newPassword     | string | Yes      | 4–128 characters |

The snake_case names `current_password` and `new_password` also work. Changing another account's password is not supported. Confirm the new password in the client before sending it.

**Request headers:**

```http
Content-Type: application/json
Authorization: Bearer <accessToken>
```

**Request body:**

```json
{
  "currentPassword": "pass1234",
  "newPassword": "newpass5678"
}
```

**Response 200:**

```json
{
  "message": "Password changed successfully"
}
```

**Response 400** (the current password does not match; no change is saved):

```json
{
  "detail": "Current password is incorrect"
}
```

Missing/invalid/expired authentication returns 401, for example `{"detail": "Bearer token required"}` when the header is missing. Missing fields, null values, non-string values, or invalid password lengths return 422 with the validation error array described in [Basics and errors](#basics-and-errors). After success, use the new password for future logins; the previous password no longer works.

### `GET /settings`

Authentication: **User**.

No path/query parameters. Missing settings are created using defaults.

**Request body:** none.

**Response 200:**

```json
{
  "themeMode": "LIGHT",
  "notificationsEnabled": true,
  "defaultPredictionType": "BOTH",
  "defaultInputMode": "GITHUB_URL"
}
```

### `PATCH /settings`

Authentication: **User**.

All fields are optional. Send values, not null. Explicit null for notificationsEnabled returns 422; omit it to keep the current value.

| Field                 | Type    | Allowed values                      |
| --------------------- | ------- | ----------------------------------- |
| themeMode             | string  | LIGHT, DARK                         |
| notificationsEnabled  | boolean | true, false                         |
| defaultPredictionType | string  | MERGE_PROBABILITY, PR_QUALITY, BOTH |
| defaultInputMode      | string  | GITHUB_URL                         |

Enums here are case-sensitive. Invalid enum values return 400, such as `Invalid theme_mode`. These are stored preferences only; they are not applied to prediction requests. `/predict` accepts GitHub PR URLs only.

**Request body:**

```json
{
  "themeMode": "DARK",
  "notificationsEnabled": false,
  "defaultPredictionType": "BOTH",
  "defaultInputMode": "GITHUB_URL"
}
```

**Response 200:**

```json
{
  "themeMode": "DARK",
  "notificationsEnabled": false,
  "defaultPredictionType": "BOTH",
  "defaultInputMode": "GITHUB_URL"
}
```

## Models, plans, and credits

Each successful prediction deducts the selected model's creditCost once, including BOTH requests. The prediction's creditsCost stores that charge. Validation and analysis-service failures do not consume credits.

Each subscription has `credits` and a `duration` in days. `endedAt` is `startedAt + duration` days (UTC). Usage belongs to that subscription. Switching plans carries creditsUsed into the new subscription; selecting the same active plan does not restart it. Expired or inactive subscriptions fall back to a fresh FREE subscription. Credits do not roll over after expiry. Remaining credits are max(0, credits - creditsUsed).

Plans list their models directly. New installations seed these defaults; existing plans and admin edits are preserved:

| Plan | Credits | Duration (days) | Models |
| --- | --- | --- | --- |
| FREE | 5 | 1 | model-1 |
| PLUS | 30 | 30 | models 1�3 |
| PRO | 100 | 30 | models 1�6 |
| ULTRA | 300 | 30 | models 1�6 |

All six catalog entries use the same hosted analyzer and start with creditCost 1. Model response fields are modelId, code, name, version, provider, description, and creditCost. Plan responses use credits and duration. Parent plans, monthlyCredits, taskType, and artifactKey have been removed. Credits and model edits apply on subsequent requests; duration edits apply when a new subscription starts.

### `GET /models`

Authentication: **User**.

Returns active models accessible through the current plan, sorted by name.

Optional query: predictionType (MERGE_PROBABILITY, PR_QUALITY, or BOTH; uppercased). All catalog models support all three values. An unsupported value returns 400. Omit the query to list all active models in the plan.

**Request body:** none.

**Response 200:** Array example shows one complete item; all matching items are returned. Empty results use `[]`.

```json
[
  {
    "modelId": "<modelId>",
    "code": "model-1",
    "name": "Model 1",
    "version": "1.0",
    "provider": "gemini-api",
    "description": "Hosted Gemini PR analysis.",
    "creditCost": 1
  }
]
```

### `GET /plans`

Authentication: **User**.

No query parameters. Active plans ordered by credits. The example shows the first plan; the default database returns four.

**Request body:** none.

**Response 200:** Array example shows one complete item; all matching items are returned. Empty results use `[]`.

```json
[
  {
    "planId": "<planId>",
    "code": "FREE",
    "name": "Free",
    "description": "5 credits per plan period",
    "models": [
      {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1",
        "version": "1.0",
        "provider": "gemini-api",
        "description": "Hosted Gemini PR analysis.",
        "creditCost": 1
      }
    ],
    "credits": 5,
    "duration": 1
  }
]
```

### `GET /subscription`

Authentication: **User**.

No path/query parameters. Returns the current ACTIVE subscription; creates a FREE subscription if none exists or it has expired. Fields: subscriptionId, status, startedAt, endedAt, and the complete plan. Usage is available from /active-plan or /dashboard.

**Request body:** none.

**Response 200:**

```json
{
  "subscriptionId": "<subscriptionId>",
  "status": "ACTIVE",
  "startedAt": "2026-10-04T12:00:00",
  "plan": {
    "planId": "<planId>",
    "code": "FREE",
    "name": "Free",
    "description": "5 credits per plan period",
    "models": [
      {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1",
        "version": "1.0",
        "provider": "gemini-api",
        "description": "Hosted Gemini PR analysis.",
        "creditCost": 1
      }
    ],
    "credits": 5,
    "duration": 1
  },
  "endedAt": "2026-10-05T12:00:00"
}
```

### `GET /active-plan`

Authentication: **User**.

No path/query parameters. Current plan plus creditsUsed and creditsRemaining. `GET /plan` is an alias with the same response. This example is before any predictions.

**Request body:** none.

**Response 200:**

```json
{
  "planId": "<planId>",
  "code": "FREE",
  "name": "Free",
  "description": "5 credits per plan period",
  "models": [
    {
      "modelId": "<modelId>",
      "code": "model-1",
      "name": "Model 1",
      "version": "1.0",
      "provider": "gemini-api",
      "description": "Hosted Gemini PR analysis.",
      "creditCost": 1
    }
  ],
  "creditsUsed": 0,
  "creditsRemaining": 5,
  "credits": 5,
  "duration": 1
}
```

### `POST /subscription`

Authentication: **User**.

Required planCode (string): an existing active plan code, uppercased by the route; avoid spaces. Accepts FREE, PLUS, PRO, ULTRA, or an active admin-created code. Cancels the current ACTIVE subscription and creates a new one with the selected duration, carrying spent credits forward. Selecting the same active plan returns the existing subscription. No payment is processed. Unknown/inactive plan returns 404: `Plan not found`. This example reselects FREE.

**Request body:**

```json
{
  "planCode": "FREE"
}
```

**Response 200:**

```json
{
  "subscriptionId": "<subscriptionId>",
  "status": "ACTIVE",
  "startedAt": "2026-10-04T12:00:00",
  "plan": {
    "planId": "<planId>",
    "code": "FREE",
    "name": "Free",
    "description": "5 credits per plan period",
    "models": [
      {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1",
        "version": "1.0",
        "provider": "gemini-api",
        "description": "Hosted Gemini PR analysis.",
        "creditCost": 1
      }
    ],
    "credits": 5,
    "duration": 1
  },
  "endedAt": "2026-10-05T12:00:00"
}
```

## Predictions and history

The backend calls `POST https://pr-predictor-backend-gemini-api.onrender.com/analyze` with only `{ "pr_url": "..." }`. Set `PR_ANALYZER_TOKEN` on the server; it is never returned to clients. The local login bearer token and the analysis-service token are different credentials. The service handles GitHub retrieval and Gemini analysis. Requests time out after 120 seconds; this backend does not retry them.

### `POST /predict`

Authentication: **User**. No path/query parameters. The request is synchronous. It checks plan/model access and credits before calling the service, saves the feature and analysis fields in PredictionResult, and charges the selected model's creditCost once. All catalog models use the same analyzer; modelId controls access/cost only.

**Request body:**

```json
{
  "pullRequestUrl": "https://github.com/owner/repo/pull/12",
  "modelId": "<model UUID from GET /models>"
}
```

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| pullRequestUrl | string | Yes | HTTPS GitHub PR URL; aliases `pr_url` and `pull_request_url` are also accepted |
| modelId | string | Yes | Model UUID from GET /models; model codes such as model-1 are not accepted |

Send a JSON object containing both the URL and modelId. A bare URL string, missing modelId, predictionType, and unknown fields return 422. An active model outside the plan returns 403; missing/inactive models return 404.

**Response 200:** the complete JSON object returned by `/analyze`, unchanged. Both prediction routes return the same structure. For example:

```json
{
  "pr_url": "https://github.com/owner/repo/pull/12",
  "features": {
    "repository": "owner/repo",
    "number": 12,
    "title": "Fix login",
    "state": "open",
    "author": "sam",
    "merged": false,
    "files": [
      {
        "filename": "app.py",
        "patch": "+fix"
      }
    ],
    "warnings": []
  },
  "analysis": {
    "merge_probability": 95,
    "quality_score": 92,
    "quality": "excellent",
    "confidence": "high",
    "summary": "Fixes login.",
    "merge_reasoning": "Small tested fix.",
    "recommendations": {
      "excellent": [
        "Tests included"
      ],
      "good": [],
      "bad": [],
      "worst": []
    },
    "potential_improvements": [],
    "limitations": [
      "No CI results"
    ]
  },
  "probability_note": "AI estimate, not a calibrated probability or a guarantee."
}
```

All service fields are returned, including any extra top-level fields and nested features, files/patches, comments, reviews, commits, checks, statuses, warnings, recommendations, improvements, limitations, and confidence. Field names and values are not renamed, filtered, or supplemented with local metadata.

Both analyzer scores are saved. Read them from `analysis.merge_probability` and `analysis.quality_score`. The response does not add `predictionId` or `creditsCost`; use `/predictions` for saved IDs and `/active-plan` for remaining credits. History stores the fields defined in PredictionResult; extra analyzer fields are returned by POST but are not saved.

**Errors (no credits charged):**

| Status | Meaning |
| --- | --- |
| 401 | Missing/invalid local login token, or the service rejected PR_ANALYZER_TOKEN (the detail distinguishes them) |
| 403 | Model access denied by the current plan |
| 409 | Subscription expired or changed while the analyzer was running |
| 404 | Missing/inactive model, inaccessible/missing PR, or missing managed service token |
| 422 | Invalid body, invalid PR URL, or rejected service request |
| 429 | Not enough credits for the selected model |
| 502 | Connection failure, upstream error, or incomplete/invalid service response |
| 503 | PR_ANALYZER_TOKEN not set, service configuration missing, service quota/rate limit, or service unavailable |
| 504 | GitHub/Gemini timeout or analysis service timeout |

Analyzer merged, draft, and mergeable fields must be JSON booleans or null when present; invalid values return 502 before credits are charged.

Analyzer failures are saved as FAILED predictions with httpStatus and errorMessage, zero creditsCost, and no result. Local validation/access/credit failures do not create prediction records.

### `POST /predict-dev`

Authentication: **Public**. Same input as POST /predict. This route calls the same external service but does not check plan access, charge credits, or save history. modelId does not select an external classifier.

**Response 200:** exactly the complete analyzer JSON shown under POST /predict, including every additional service field. No wrapper or local fields are added. It can return the same service errors, but not local login/plan/credit errors.

### `GET /history` and `GET /predictions`

Authentication: **User**. Request body: none. Query: optional `search` (matches stored PR URL/title), `limit` (integer 1–100, default 20).

**Response 200:** an array of local history records for the current user, newest first. Empty history is `[]`. Each item includes local metadata plus features and analysis read from PredictionResult. Reading history does not call the analyzer. Fields absent from the analyzer response are null; failed predictions have empty features/analysis objects. predictionType, modelVersion, inferenceKey, repository, and pullRequest are no longer top-level history fields. Repository and PR metadata are inside features.

One history item (nullable feature fields omitted here for readability):

```json
{
  "predictionId": "<predictionId>",
  "status": "COMPLETED",
  "createdAt": "2026-10-29T12:00:00",
  "completedAt": "2026-10-29T12:00:02",
  "creditsCost": 1,
  "httpStatus": 200,
  "errorMessage": null,
  "model": {
    "modelId": "<modelId>",
    "code": "model-1",
    "name": "Model 1",
    "version": "1.0",
    "provider": "gemini-api",
    "description": "Hosted Gemini PR analysis.",
    "creditCost": 1,
    "active": true,
    "createdAt": "2026-10-29T12:00:00",
    "retiredAt": null
  },
  "pr_url": "https://github.com/owner/repo/pull/12",
  "title": "Fix login",
  "features": {
    "pr_url": "https://github.com/owner/repo/pull/12",
    "repository": "owner/repo",
    "number": 12,
    "title": "Fix login",
    "state": "open",
    "author": "sam",
    "merged": false,
    "created_at": "2026-10-28T12:00:00",
    "updated_at": "2026-10-29T12:00:00",
    "files": [
      {
        "filename": "app.py",
        "patch": "+fix"
      }
    ]
  },
  "analysis": {
    "merge_probability": 95,
    "quality_score": 92,
    "quality": "excellent",
    "confidence": "high",
    "summary": "Fixes login.",
    "merge_reasoning": "Small tested fix.",
    "recommendations": {
      "excellent": [
        "Tests included"
      ],
      "good": [],
      "bad": [],
      "worst": []
    },
    "potential_improvements": [],
    "limitations": [
      "No CI results"
    ]
  },
  "mergeProbability": 95,
  "qualityScore": 92,
  "qualityLabel": "excellent",
  "recommendation": "Fixes login.",
  "probabilityNote": "AI estimate, not a calibrated probability or a guarantee."
}
```

Both scores are stored for every successful prediction. `features.number` comes from pr_number; `features.created_at` and `features.updated_at` come from pr_created_at and pr_updated_at. Feature lists and analysis recommendations are stored as JSON. `predictionId` is the local ID used by the detail route.

### `GET /predictions/{predictionId}`

Authentication: **User**. Required path: predictionId, the UUID returned by GET /history. No body/query. **Response 200:** one local history record in the shape shown above. Unknown IDs or another user's prediction return 404.

### `GET /dashboard`

Authentication: **User**. No body/path/query input.

**Response 200:**

```json
{
  "totalPredictions": 0,
  "averageMergeProbability": null,
  "usage": {
    "predictionsUsed": 0,
    "creditsUsed": 0,
    "creditLimit": 5,
    "creditsRemaining": 5
  },
  "subscription": {
    "subscriptionId": "<subscriptionId>",
    "status": "ACTIVE",
    "startedAt": "2026-10-28T12:00:00",
    "plan": {
      "planId": "<planId>",
      "code": "FREE",
      "name": "Free",
      "description": "5 credits per plan period",
      "models": [
        {
          "modelId": "<modelId>",
          "code": "model-1",
          "name": "Model 1",
          "version": "1.0",
          "provider": "gemini-api",
          "description": "Hosted Gemini PR analysis.",
          "creditCost": 1
        }
      ],
      "credits": 5,
      "duration": 1
    },
    "endedAt": "2026-10-29T12:00:00"
  },
  "recentPredictions": []
}
```

Counts saved predictions, averages stored non-null mergeProbability values, and returns up to five complete prediction objects in recentPredictions. The average is null with no scored entries. Usage is for the current subscription. predictionsUsed counts its saved predictions; creditsUsed also includes credits carried over when changing plans.

## Private admin routes

Log in through /login with an admin account. The seeded username is admin; its initial password comes from ADMIN_PASSWORD (default 1234). There is no separate admin-login route.

### Model write fields

POST requires code, name, version. PATCH accepts the same fields, all optional.

| Field       | Type           | Create default / rules                                            |
| ----------- | -------------- | ----------------------------------------------------------------- |
| code        | string         | Required; 2–80 characters; trimmed/lowercased, unique             |
| name        | string         | Required; 1–150 characters; trimmed, not blank                    |
| version     | string         | Required; 1–80 characters; trimmed, not blank                     |
| provider    | string or null | null                                                              |
| description | string or null | null                                                              |
| creditCost  | integer        | 1; range 1–100000                                                 |
| active      | boolean        | true                                                              |

No classifier selection or training occurs. provider defaults to local and must be a string. description can be cleared with null. Omit other nonnullable fields or provide a valid value, not null.

Admin model responses extend public model objects with active (boolean), createdAt (timestamp), and retiredAt (timestamp or null). Deactivation sets retiredAt; reactivation clears it.

### Plan write fields

POST requires code and name; credits defaults to 5 and duration defaults to 1 day. PATCH accepts the same fields, all optional. Plan codes must have 2-80 characters after trimming; blank or invalid-length codes return 422 on both create and update.

| Field          | Type             | Create default / rules                                           |
| -------------- | ---------------- | ---------------------------------------------------------------- |
| code           | string           | Required; 2–80 characters; trimmed/uppercased, unique            |
| name           | string           | Required; 1–150 characters; trimmed, not blank                   |
| credits | integer | Default 5; range 0�1000000000 |
| duration | integer | Default 1; range 1�36500 days |
| modelCodes     | array of strings | []; existing model codes, trimmed/lowercased; duplicates removed |
| description    | string or null   | Empty string if absent/null on create                            |
| active         | boolean          | true                                                             |

modelCodes replaces the assigned list; it does not append. On PATCH, [] or null clears models. Omit other fields to keep them; use an empty description string to clear it on PATCH.

Admin plan responses extend public plans with active. models contains the assigned model objects. Actual model activity is enforced by /models and /predict.

### `GET /admin/api/stats`

Authentication: **Admin**.

No path/query parameters. Counts all users/predictions and only active models/plans.

**Request body:** none.

**Response 200:**

```json
{
  "users": 2,
  "predictions": 1,
  "models": 6,
  "plans": 4
}
```

### `GET /admin/api/models`

Authentication: **Admin**.

No path/query parameters. All catalog models including inactive records, active first and then by name.

**Request body:** none.

**Response 200:** Array example shows one complete item; all matching items are returned. Empty results use `[]`.

```json
[
  {
    "modelId": "<modelId>",
    "code": "model-1",
    "name": "Model 1",
    "version": "1.0",
    "provider": "gemini-api",
    "description": "Hosted Gemini PR analysis.",
    "creditCost": 1,
    "active": true,
    "createdAt": "2026-10-04T12:00:00",
    "retiredAt": null
  }
]
```

### `POST /admin/api/models`

Authentication: **Admin**.

Creates a catalog record using the model write fields above. Assign it to a plan before users can select it. Duplicate code: 409. Blank code/name/version: 400. Invalid schema length/range: 422.

**Request body:**

```json
{
  "code": "student-model",
  "name": "Student Model",
  "version": "1.0",
  "provider": "gemini-api",
  "description": "Hosted PR analysis for the student plan.",
  "creditCost": 2,
  "active": true
}
```

**Response 201:**

```json
{
  "modelId": "<modelId>",
  "code": "student-model",
  "name": "Student Model",
  "version": "1.0",
  "provider": "gemini-api",
  "description": "Hosted PR analysis for the student plan.",
  "creditCost": 2,
  "active": true,
  "createdAt": "2026-10-04T12:00:00",
  "retiredAt": null
}
```

### `PATCH /admin/api/models/{modelId}`

Authentication: **Admin**.

Required path modelId: database UUID, not model code. Changes only included fields. Unknown ID: 404. Duplicate code: 409. Blank code/name/version: 400. Cost changes apply to future predictions; past creditsCost stays unchanged.

**Request body:**

```json
{
  "name": "Student Model Updated",
  "creditCost": 3,
  "active": true
}
```

**Response 200:**

```json
{
  "modelId": "<modelId>",
  "code": "student-model",
  "name": "Student Model Updated",
  "version": "1.0",
  "provider": "gemini-api",
  "description": "Hosted PR analysis for the student plan.",
  "creditCost": 3,
  "active": true,
  "createdAt": "2026-10-04T12:00:00",
  "retiredAt": null
}
```

### `DELETE /admin/api/models/{modelId}`

Authentication: **Admin**.

Required path modelId: database UUID. No query parameters. Deactivates the model without deleting history. Unknown ID: 404. Reactivate using PATCH with {"active": true}.

**Request body:** none.

**Response 200:**

```json
{
  "message": "Model deactivated",
  "model": {
    "modelId": "<modelId>",
    "code": "student-model",
    "name": "Student Model Updated",
    "version": "1.0",
    "provider": "gemini-api",
    "description": "Hosted PR analysis for the student plan.",
    "creditCost": 3,
    "active": false,
    "createdAt": "2026-10-04T12:00:00",
    "retiredAt": "2026-10-04T12:00:00"
  }
}
```

### `GET /admin/api/plans`

Authentication: **Admin**.

No path/query parameters. All plans, including inactive ones, ordered by credits.

**Request body:** none.

**Response 200:** Array example shows one complete item; all matching items are returned. Empty results use `[]`.

```json
[
  {
    "planId": "<planId>",
    "code": "FREE",
    "name": "Free",
    "description": "5 credits per plan period",
    "active": true,
    "models": [
      {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1",
        "version": "1.0",
        "provider": "gemini-api",
        "description": "Hosted Gemini PR analysis.",
        "creditCost": 1
      }
    ],
    "credits": 5,
    "duration": 1
  }
]
```

### `POST /admin/api/plans`

Authentication: **Admin**.

Creates a plan using the plan write fields above. Duplicate code: 409. Unknown parent/model: 404 (`Parent plan not found` or `Model not found: <code>`). Blank name: 400.

**Request body:**

```json
{
  "code": "STUDENT",
  "name": "Student",
  "modelCodes": [
    "model-1"
  ],
  "description": "20 credits per plan period",
  "active": true,
  "credits": 20,
  "duration": 30
}
```

**Response 201:**

```json
{
  "planId": "<planId>",
  "code": "STUDENT",
  "name": "Student",
  "description": "20 credits per plan period",
  "active": true,
  "models": [
    {
      "modelId": "<modelId>",
      "code": "model-1",
      "name": "Model 1",
      "version": "1.0",
      "provider": "gemini-api",
      "description": "Hosted Gemini PR analysis.",
      "creditCost": 1
    }
  ],
  "credits": 20,
  "duration": 30
}
```

### `PATCH /admin/api/plans/{planId}`

Authentication: **Admin**.

Required path planId: database UUID, not code. This example assigns model-1 directly. Unknown plan/model: 404. Duplicate code: 409. FREE cannot be renamed or deactivated (400). Blank name: 400. Credit changes affect current allowance without resetting usage.

**Request body:**

```json
{
  "modelCodes": [
    "model-1"
  ],
  "description": "40 credits per plan period",
  "credits": 40,
  "duration": 30
}
```

**Response 200:**

```json
{
  "planId": "<planId>",
  "code": "STUDENT",
  "name": "Student",
  "description": "40 credits per plan period",
  "active": true,
  "models": [
    {
      "modelId": "<modelId>",
      "code": "model-1",
      "name": "Model 1",
      "version": "1.0",
      "provider": "gemini-api",
      "description": "Hosted Gemini PR analysis.",
      "creditCost": 1
    }
  ],
  "credits": 40,
  "duration": 30
}
```

### `DELETE /admin/api/plans/{planId}`

Authentication: **Admin**.

Required path planId: database UUID. No query parameters. Sets active=false; unknown ID returns 404. Deleting FREE returns 400: `The FREE plan cannot be deleted`. Inactive plans disappear from /plans and cannot be newly selected. Users with an inactive plan receive a new FREE subscription on their next plan-dependent request. Reactivate with PATCH and {"active": true}.

**Request body:** none.

**Response 200:**

```json
{
  "message": "Plan deactivated",
  "plan": {
    "planId": "<planId>",
    "code": "STUDENT",
    "name": "Student",
    "description": "40 credits per plan period",
    "active": false,
    "models": [
      {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1",
        "version": "1.0",
        "provider": "gemini-api",
        "description": "Hosted Gemini PR analysis.",
        "creditCost": 1
      }
    ],
    "credits": 40,
    "duration": 30
  }
}
```

### `GET /admin/api/users`

Authentication: **Admin**.

No path/query parameters. All users, newest first. Each entry has the public account fields from /me. Password hashes are never returned.

**Request body:** none.

**Response 200:** Array example shows one complete item; all matching items are returned. Empty results use `[]`.

```json
[
  {
    "userId": "<userId>",
    "username": "sam",
    "email": "sam.updated@example.com",
    "fullName": "Sam Student Updated",
    "role": "USER",
    "githubProfileUrl": null,
    "createdAt": "2026-10-04T12:00:00"
  }
]
```

### `PATCH /admin/api/users/{userId}/role`

Authentication: **Admin**.

Required path userId: database UUID. Required body role: USER or ADMIN (string, uppercased). Missing/invalid role returns 400: `role must be USER or ADMIN`. Unknown user returns 404: `User not found`. Future authorization reads the updated database role.

**Request body:**

```json
{
  "role": "ADMIN"
}
```

**Response 200:**

```json
{
  "userId": "<userId>",
  "username": "sam",
  "email": "sam.updated@example.com",
  "fullName": "Sam Student Updated",
  "role": "ADMIN",
  "githubProfileUrl": null,
  "createdAt": "2026-10-04T12:00:00"
}
```

### `GET /admin/api/predictions`

Authentication: **Admin**.

No path/query parameters. Latest 100 prediction summaries across all users, newest first. username can be null when no related user is available. These are summaries rather than full prediction objects.

**Request body:** none.

**Response 200:** Array example shows one complete item; all matching items are returned. Empty results use `[]`.

```json
[
  {
    "predictionId": "<predictionId>",
    "username": "sam",
    "status": "COMPLETED",
      "createdAt": "2026-10-04T12:00:00"
  }
]
```

## Browser pages

| Route                  | Authentication                   | Request data | Response                                                     |
| ---------------------- | -------------------------------- | ------------ | ------------------------------------------------------------ |
| `GET /admin/`          | Public page; data requires Admin | None         | 200 text/html admin console                                  |
| `GET /admin/admin.css` | Public                           | None         | CSS asset                                                    |
| `GET /admin/admin.js`  | Public                           | None         | JavaScript asset                                             |
| `GET /docs`            | Public                           | None         | 200 text/html Swagger UI (interactive OpenAPI documentation) |
| `GET /redoc`           | Public                           | None         | 200 text/html ReDoc UI                                       |
| `GET /openapi.json`    | Public                           | None         | 200 application/json generated schema                        |

The admin page signs in through /login and calls /admin/api/\*. Its Change password form calls `POST /change-password` for the signed-in admin and checks password confirmation before submitting. When opened through a separate static server (for example VS Code Live Server), its api-base meta tag defaults to http://127.0.0.1:8000. Start the backend before signing in.

All private admin routes have controls in the admin page:

| Method | Route | Frontend control |
| ------ | ----- | ---------------- |
| GET | `/admin/api/stats` | Dashboard counts |
| GET | `/admin/api/users` | Users table |
| PATCH | `/admin/api/users/{userId}/role` | Role selector and Save |
| GET | `/admin/api/predictions` | Recent predictions table |
| GET | `/admin/api/models` | Prediction models table |
| POST | `/admin/api/models` | New model and Save model |
| PATCH | `/admin/api/models/{modelId}` | Edit / Activate model |
| DELETE | `/admin/api/models/{modelId}` | Delete model (deactivate) |
| GET | `/admin/api/plans` | Plans table |
| POST | `/admin/api/plans` | New plan and Save plan |
| PATCH | `/admin/api/plans/{planId}` | Edit / Activate plan |
| DELETE | `/admin/api/plans/{planId}` | Delete plan (deactivate) |

OpenAPI describes request validation. Many handlers return plain dictionaries without response models, so this document supplies the response examples.

## Python prediction helper

`analysis_api.analyze_pr(pull_request_url)` performs the single service call using PR_ANALYZER_TOKEN and returns its complete JSON object. It raises an HTTPException with the documented status on failure. The local model-training and GitHub-feature helpers have been removed.

## Client example

1. Register or log in; store accessToken.
2. Send the bearer header on protected calls.
3. GET /active-plan to display credits and GET /models to show available models/costs.
4. POST /predict with a GitHub PR URL (`pullRequestUrl`) and the selected model UUID (`modelId`).
5. Refresh /active-plan after success; use /history and /predictions/{predictionId} for saved results.
6. Use GET /plans and POST /subscription to switch plans.

PowerShell example with an existing account:

```powershell
$apiBase = "http://127.0.0.1:8000"
$loginBody = @{ username = "sam"; password = "pass1234" } | ConvertTo-Json
$session = Invoke-RestMethod -Method Post -Uri "$apiBase/login" -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($session.accessToken)" }
Invoke-RestMethod -Uri "$apiBase/active-plan" -Headers $headers
$models = Invoke-RestMethod -Uri "$apiBase/models" -Headers $headers
$predictionBody = @{
    pullRequestUrl = "https://github.com/owner/repository/pull/123"
    modelId = $models[0].modelId
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$apiBase/predict" -Headers $headers -ContentType "application/json" -Body $predictionBody
```

The account must exist, have at least one available model, and have enough credits. Use the error table to handle unsuccessful responses.
