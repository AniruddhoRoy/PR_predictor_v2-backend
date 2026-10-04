# PR Predictor API documentation

Base URL: `http://127.0.0.1:8000`

This reference follows `app.py`, `schemas.py`, and `prediction_engine.py`. It includes request fields, response examples, authentication, and errors for every application route.

## Contents

- [Basics and errors](#basics-and-errors)
- [Public routes](#public-routes)
- [Profile and settings](#profile-and-settings)
- [Models, plans, and credits](#models-plans-and-credits)
- [Predictions and history](#predictions-and-history)
- [Admin routes](#admin-routes)
- [Browser pages](#browser-pages)
- [Client example](#client-example)

## Basics and errors

Send bodies with `Content-Type: application/json`. Responses are JSON except browser pages and assets. Use camelCase fields as shown; Pydantic request models also accept their snake_case Python field names. Extra Pydantic request fields are ignored, not applied to database records.

| Authentication label | Required header | Access |
| --- | --- | --- |
| Public | None | Anyone |
| User | `Authorization: Bearer <accessToken>` | Signed-in users, including admins |
| Admin | `Authorization: Bearer <accessToken>` | Account whose current database role is ADMIN |

Get accessToken from registration or login. Treat it as an opaque string. Default expiry is 12 hours, configurable through TOKEN_TTL_SECONDS. There is no refresh-token or logout route; sign in again after expiry and remove the stored token on client logout.

Examples use placeholders such as `<userId>` for generated UUID strings. Replace path placeholders with IDs returned by the API. Timestamps and scores are illustrative. Current timestamps are UTC ISO strings without a timezone suffix. Scores are percentages from 0 to 100. Arrays have no `data` wrapper.

For PATCH, omit unchanged fields. Optional does not mean every field safely accepts null; use null only where explicitly described below.

Application errors have a string detail:

```json
{"detail": "Not enough credits for this model"}
```

Validation errors normally have an array detail, for example a missing login password:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "password"],
      "msg": "Field required",
      "input": {"username": "sam"}
    }
  ]
}
```

Exact validation fields can vary with FastAPI/Pydantic versions. Handle both detail shapes.

| Status | Meaning |
| --- | --- |
| 200 | Successful read/update/prediction/deactivation |
| 201 | Account/model/plan created |
| 400 | Unsupported value or invalid operation |
| 401 | Missing/invalid/expired token, deleted account, or incorrect login |
| 403 | Admin access required, or selected prediction model inaccessible/incompatible |
| 404 | Record, model, or plan not found |
| 409 | Duplicate account/code or inheritance cycle |
| 422 | Missing required field, malformed body, or schema validation error |
| 429 | Not enough monthly credits |
| 502 | GitHub data retrieval failed |
| 503 | Notebook inference unavailable; no credits charged |

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

Creates a USER, default settings, and a FREE subscription when the active FREE plan exists. Signs the user in immediately.

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| username | string | Yes | 3–80 characters; trimmed/lowercased |
| email | string | Yes | 5–255 characters; trimmed/lowercased; no email-format validator |
| password | string | Yes | 4–128 characters |
| fullName | string | Yes | 1–150 characters before trimming |
| githubProfileUrl | string or null | No | Default null; no URL-format validator |

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

All fields are optional: fullName (string), email (string), githubProfileUrl (string or null). Null clears githubProfileUrl. Send a string for email; duplicate email returns 409: `Email is already registered`. Email is trimmed/lowercased, fullName is trimmed. This route cannot change username, password, or role.

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

All fields are optional. Send values, not null.

| Field | Type | Allowed values |
| --- | --- | --- |
| themeMode | string | LIGHT, DARK |
| notificationsEnabled | boolean | true, false |
| defaultPredictionType | string | MERGE_PROBABILITY, PR_QUALITY, BOTH |
| defaultInputMode | string | GITHUB_URL, MANUAL_FEATURES |

Enums here are case-sensitive. Invalid enum values return 400, such as `Invalid theme_mode`. These are stored preferences; a prediction object must still include inputType and predictionType.

**Request body:**

```json
{
  "themeMode": "DARK",
  "notificationsEnabled": false,
  "defaultPredictionType": "BOTH",
  "defaultInputMode": "MANUAL_FEATURES"
}
```

**Response 200:**

```json
{
  "themeMode": "DARK",
  "notificationsEnabled": false,
  "defaultPredictionType": "BOTH",
  "defaultInputMode": "MANUAL_FEATURES"
}
```

## Models, plans, and credits

Each successful prediction deducts the selected model's creditCost once, including BOTH requests. The prediction's creditsCost stores that charge. Validation, GitHub retrieval, and inference failures do not consume credits.

Usage is per user/calendar month, using the server's local date. Each month starts a new usage period; credits do not roll over. Switching plans changes the limit but preserves that month's creditsUsed. Remaining credits are max(0, monthlyCredits - creditsUsed). Admin edits apply to subsequent requests and survive startup.

Plans inherit parent models recursively and add their own direct models, with duplicates removed. Credits are the plan's own allowance; parent credits are not added.

Default values (admins may change them):

| Plan | Monthly credits | Parent | Direct models | Effective models |
| --- | --- | --- | --- | --- |
| FREE | 5 | None | model-1 | model-1 |
| PLUS | 30 | None | model-1, model-2, model-3 | models 1–3 |
| PRO | 100 | PLUS | model-4, model-5, model-6 | models 1–6 |
| ULTRA | 300 | PRO | None | models 1–6 |

| Model code | artifactKey | Classifier |
| --- | --- | --- |
| model-1 | logistic-regression | Logistic Regression |
| model-2 | random-forest | Random Forest |
| model-3 | knn | K-nearest neighbors |
| model-4 | decision-tree | Decision Tree |
| model-5 | sgd-classifier | SGD Classifier |
| model-6 | extra-trees | Extra Trees |

Seeded models have taskType BOTH and creditCost 1. Models 1–5 match the notebook; model 6 is the additional Extra Trees classifier configured in the backend.

Model response fields: modelId (UUID), code/name (strings), taskType (supported request type), version (catalog metadata), provider/description (nullable strings), creditCost (positive integer), artifactKey (nullable inference selector). Changing version alone does not retrain a classifier.

Plan response fields: planId/code/name, monthlyCredits (nonnegative integer), description, parentPlanCode (string or null), and models (complete public model objects, including inherited models). Plan model lists can include deactivated models. Use GET /models for active usable models.

### `GET /models`

Authentication: **User**.

Returns active models accessible through the current plan, sorted by name.

Optional query: predictionType (string), intended values MERGE_PROBABILITY, PR_QUALITY, BOTH; uppercased. Models match if taskType is BOTH or equals the filter. BOTH requests only select BOTH models. Unknown filter values are not rejected here and may still return BOTH models. Omit the query for all active models in the plan.

**Request body:** none.

**Response 200:** Array example shows one complete item; all matching items are returned. Empty results use `[]`.

```json
[
  {
    "modelId": "<modelId>",
    "code": "model-1",
    "name": "Model 1 - Logistic Regression",
    "taskType": "BOTH",
    "version": "1.0",
    "provider": "notebook",
    "description": "Classifier trained from models(notebook)/final_df.csv.",
    "creditCost": 1,
    "artifactKey": "logistic-regression"
  }
]
```

### `GET /plans`

Authentication: **User**.

No query parameters. Active plans ordered by monthlyCredits. The example shows the first plan; the default database returns four.

**Request body:** none.

**Response 200:** Array example shows one complete item; all matching items are returned. Empty results use `[]`.

```json
[
  {
    "planId": "<planId>",
    "code": "FREE",
    "name": "Free",
    "monthlyCredits": 5,
    "description": "5 credits each month",
    "parentPlanCode": null,
    "models": [
      {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1 - Logistic Regression",
        "taskType": "BOTH",
        "version": "1.0",
        "provider": "notebook",
        "description": "Classifier trained from models(notebook)/final_df.csv.",
        "creditCost": 1,
        "artifactKey": "logistic-regression"
      }
    ]
  }
]
```

### `GET /subscription`

Authentication: **User**.

No path/query parameters. Returns the current ACTIVE subscription; creates a FREE subscription if none exists. Fields: subscriptionId, status, startedAt, and the complete plan. Usage is available from /active-plan or /dashboard.

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
    "monthlyCredits": 5,
    "description": "5 credits each month",
    "parentPlanCode": null,
    "models": [
      {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1 - Logistic Regression",
        "taskType": "BOTH",
        "version": "1.0",
        "provider": "notebook",
        "description": "Classifier trained from models(notebook)/final_df.csv.",
        "creditCost": 1,
        "artifactKey": "logistic-regression"
      }
    ]
  }
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
  "monthlyCredits": 5,
  "description": "5 credits each month",
  "parentPlanCode": null,
  "models": [
    {
      "modelId": "<modelId>",
      "code": "model-1",
      "name": "Model 1 - Logistic Regression",
      "taskType": "BOTH",
      "version": "1.0",
      "provider": "notebook",
      "description": "Classifier trained from models(notebook)/final_df.csv.",
      "creditCost": 1,
      "artifactKey": "logistic-regression"
    }
  ],
  "creditsUsed": 0,
  "creditsRemaining": 5
}
```

### `POST /subscription`

Authentication: **User**.

Required planCode (string): an existing active plan code, uppercased by the route; avoid spaces. Accepts FREE, PLUS, PRO, ULTRA, or an active admin-created code. Cancels existing ACTIVE subscriptions and creates a new one. Monthly usage is retained even if selecting the same plan again. No payment is processed. Unknown/inactive plan returns 404: `Plan not found`. This example reselects FREE.

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
    "monthlyCredits": 5,
    "description": "5 credits each month",
    "parentPlanCode": null,
    "models": [
      {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1 - Logistic Regression",
        "taskType": "BOTH",
        "version": "1.0",
        "provider": "notebook",
        "description": "Classifier trained from models(notebook)/final_df.csv.",
        "creditCost": 1,
        "artifactKey": "logistic-regression"
      }
    ]
  }
}
```

## Predictions and history

### Prediction request fields

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| inputType | string | Yes for object body | GITHUB_URL or MANUAL_FEATURES |
| predictionType | string | Yes for object body | MERGE_PROBABILITY, PR_QUALITY, BOTH |
| modelId | string or null | No | Active allowed model UUID or code; absent/null selects earliest-created compatible model in the plan |
| pullRequestUrl | string or null | For GITHUB_URL | GitHub PR URL |
| features | object or null | For MANUAL_FEATURES | Nonempty object; recognized fields below |

inputType and predictionType are uppercased. An active model excluded by the plan or incompatible with predictionType receives the same 403 plan-access error. A BOTH model supports all three request types. A specific-task model cannot handle BOTH.

### Manual feature fields

| Notebook name | Accepted aliases | Meaning / type |
| --- | --- | --- |
| title_word_count | titleWordCount | number; title words |
| body_word_count | bodyWordCount | number; description words |
| total_lines_added | totalLinesAdded, additions | number; added lines |
| total_lines_deleted | totalLinesDeleted, deletions | number; deleted lines |
| total_lines_changed | totalLinesChanged | number; added + deleted lines |
| total_files_touched | totalFilesTouched, changedFiles | number; changed files |
| files_added | filesAdded | number; added files |
| files_modified | filesModified | number; modified files |
| files_deleted | filesDeleted | number; deleted files |
| total_commits | totalCommits | number; commits |
| stars | None | number; repository stars |
| forks | None | number; repository forks |
| agent | None | string; agent category |
| task_type | taskType | string; PR task category, separate from predictionType |
| language | None | string; repository language |

Missing numeric fields become 0. Numeric strings are converted when possible; invalid values fall through to another alias or 0. When total_lines_changed is absent or 0, added/deleted lines are summed. Missing categories become unknown; unseen categories are allowed. Supply meaningful finite nonnegative counts. Additional fields such as testsAdded are stored but are not used by the notebook classifiers. When both forms exist, the notebook field takes precedence.

### GitHub feature behavior

URLs must have the shape https://github.com/owner/repo/pull/12. Optional trailing slash and http are accepted. The backend fetches PR, repository, and file data, derives numeric features, and uses unknown for agent/task_type. Language comes from the repository or defaults to unknown. Set GITHUB_TOKEN on the server for private repositories or higher API limits; it is not a request field.

Stored pullRequest display metadata currently uses `Pull request #<number>`, state OPEN, and repository owner as authorLogin. These are display placeholders even though inference uses actual GitHub features.

### Model and score behavior

The first call loads a pipeline from `trained_models/<classifier-name>.joblib`, or trains from `models(notebook)/final_df.csv` and caches it in memory. The initial call can be slower. Creating a catalog model does not train/upload a new classifier.

The notebook predicts merge status. qualityScore currently reuses mergeProbability; there is no separately trained quality classifier. BOTH returns equal scores. MERGE_PROBABILITY returns null qualityScore; PR_QUALITY returns null mergeProbability. qualityLabel is still returned for all types: Excellent >= 80, Good >= 65, Needs review >= 50, otherwise Risky. Recommendations and factors are simple summaries, not model feature-attribution explanations.

Prediction response fields:

| Field | Type | Meaning |
| --- | --- | --- |
| predictionId | string | Saved prediction UUID |
| status | string | COMPLETED for successful requests |
| predictionType | string | Requested type |
| createdAt, completedAt | string or null | Timestamps |
| modelVersion | string | Model version snapshot |
| creditsCost | integer | Charge at prediction time |
| inferenceKey | string or null | Inference selector snapshot |
| model | object or null | Current public catalog model fields |
| repository | object or null | owner, name, url; null for manual input |
| pullRequest | object or null | number, url, title, state, authorLogin; null for manual input |
| mergeProbability, qualityScore | number or null | Percentages, depending on predictionType |
| qualityLabel | string or null | Score label |
| recommendation | string or null | Review suggestion |
| factors | array | Objects with name, description, impact, order |

Model catalog fields can change later; snapshot fields retain the original version and charge.

### `POST /predict`

Authentication: **User**.

No path/query parameters. Runs synchronously, saves a completed prediction, and charges once. This manual example uses an illustrative score; actual results depend on the classifier and features. The seeded model costs 1 credit.

**Request body:**

```json
{
  "inputType": "MANUAL_FEATURES",
  "predictionType": "BOTH",
  "modelId": "<modelId>",
  "features": {
    "titleWordCount": 6,
    "bodyWordCount": 45,
    "additions": 150,
    "deletions": 25,
    "totalLinesChanged": 175,
    "changedFiles": 4,
    "filesAdded": 1,
    "filesModified": 3,
    "filesDeleted": 0,
    "totalCommits": 2,
    "stars": 100,
    "forks": 20,
    "agent": "unknown",
    "taskType": "fix",
    "language": "Python"
  }
}
```

**Response 200:**

```json
{
  "predictionId": "<predictionId>",
  "status": "COMPLETED",
  "predictionType": "BOTH",
  "createdAt": "2026-10-04T12:00:00",
  "completedAt": "2026-10-04T12:00:00",
  "modelVersion": "1.0",
  "creditsCost": 1,
  "inferenceKey": "logistic-regression",
  "model": {
    "modelId": "<modelId>",
    "code": "model-1",
    "name": "Model 1 - Logistic Regression",
    "taskType": "BOTH",
    "version": "1.0",
    "provider": "notebook",
    "description": "Classifier trained from models(notebook)/final_df.csv.",
    "creditCost": 1,
    "artifactKey": "logistic-regression"
  },
  "repository": null,
  "pullRequest": null,
  "mergeProbability": 78.5,
  "qualityScore": 78.5,
  "qualityLabel": "Good",
  "recommendation": "Looks ready for review. Keep the existing tests and ask a reviewer to verify the edge cases.",
  "factors": [
    {
      "name": "Change size",
      "description": "4 files and 175 changed lines were considered.",
      "impact": "POSITIVE",
      "order": 0
    },
    {
      "name": "Repository context",
      "description": "The notebook model used Python and fix as categorical features.",
      "impact": "NEUTRAL",
      "order": 1
    }
  ]
}
```

The same endpoint accepts this GitHub request:

```json
{
  "inputType": "GITHUB_URL",
  "predictionType": "MERGE_PROBABILITY",
  "modelId": "model-1",
  "pullRequestUrl": "https://github.com/owner/repo/pull/12"
}
```

The response has the same full prediction shape. qualityScore is null for this request, and the following fields are populated instead of null:

```json
{
  "repository": {
    "owner": "owner",
    "name": "repo",
    "url": "https://github.com/owner/repo"
  },
  "pullRequest": {
    "number": 12,
    "url": "https://github.com/owner/repo/pull/12",
    "title": "Pull request #12",
    "state": "OPEN",
    "authorLogin": "owner"
  }
}
```

This block is only the GitHub-specific part of the response. All other prediction fields are included as shown in the full example above.

A quoted JSON string body is also supported as shorthand for GITHUB_URL, BOTH, and automatic model selection:

```json
"https://github.com/owner/repo/pull/12"
```

Use application/json and include the quotes; an unquoted text body is not this shorthand.

| Status | Prediction-specific detail |
| --- | --- |
| 400 | `inputType must be GITHUB_URL or MANUAL_FEATURES` |
| 400 | `predictionType must be MERGE_PROBABILITY, PR_QUALITY, or BOTH` |
| 400 | `pullRequestUrl is required for GITHUB_URL` |
| 400 | `Use a GitHub pull request URL such as https://github.com/owner/repo/pull/12` |
| 400 | `features must contain at least one value for MANUAL_FEATURES` |
| 403 | `Your active plan does not include this model` (also used for incompatible active models) |
| 404 | `Prediction model not found` (unknown/inactive selection) |
| 404 | `Your active plan has no model for this prediction type` (automatic selection failed) |
| 429 | `Not enough credits for this model` |
| 502 | `Cannot read GitHub PR; check the URL or GITHUB_TOKEN` |
| 503 | `Notebook model is unavailable; no credits were charged` |

Invalid request shapes can return 422 before route logic runs. Unsupported artifactKey or unavailable training data can cause 503. Failed prediction requests do not return a saved failed-prediction object.

### `GET /history`

Authentication: **User**.

Current user's complete predictions, newest first. `GET /predictions` is an alias.

| Query | Type | Required | Rules/default |
| --- | --- | --- | --- |
| search | string | No | Case-insensitive match on stored PR URL/title |
| limit | integer | No | Default 20, range 1–100 |

Example: `/history?search=repo&limit=10`. Manual predictions have no PR URL/title and do not match a nonempty search. There is no page/offset parameter. Invalid limit returns 422.

**Request body:** none.

**Response 200:** Array example shows one complete item; all matching items are returned. Empty results use `[]`.

```json
[
  {
    "predictionId": "<predictionId>",
    "status": "COMPLETED",
    "predictionType": "BOTH",
    "createdAt": "2026-10-04T12:00:00",
    "completedAt": "2026-10-04T12:00:00",
    "modelVersion": "1.0",
    "creditsCost": 1,
    "inferenceKey": "logistic-regression",
    "model": {
      "modelId": "<modelId>",
      "code": "model-1",
      "name": "Model 1 - Logistic Regression",
      "taskType": "BOTH",
      "version": "1.0",
      "provider": "notebook",
      "description": "Classifier trained from models(notebook)/final_df.csv.",
      "creditCost": 1,
      "artifactKey": "logistic-regression"
    },
    "repository": null,
    "pullRequest": null,
    "mergeProbability": 78.5,
    "qualityScore": 78.5,
    "qualityLabel": "Good",
    "recommendation": "Looks ready for review. Keep the existing tests and ask a reviewer to verify the edge cases.",
    "factors": [
      {
        "name": "Change size",
        "description": "4 files and 175 changed lines were considered.",
        "impact": "POSITIVE",
        "order": 0
      },
      {
        "name": "Repository context",
        "description": "The notebook model used Python and fix as categorical features.",
        "impact": "NEUTRAL",
        "order": 1
      }
    ]
  }
]
```

### `GET /predictions/{predictionId}`

Authentication: **User**.

Required path predictionId: UUID string from predict/history. No query parameters. Returns only a prediction owned by the caller. Unknown ID or another user's prediction returns 404: `Prediction not found`.

**Request body:** none.

**Response 200:**

```json
{
  "predictionId": "<predictionId>",
  "status": "COMPLETED",
  "predictionType": "BOTH",
  "createdAt": "2026-10-04T12:00:00",
  "completedAt": "2026-10-04T12:00:00",
  "modelVersion": "1.0",
  "creditsCost": 1,
  "inferenceKey": "logistic-regression",
  "model": {
    "modelId": "<modelId>",
    "code": "model-1",
    "name": "Model 1 - Logistic Regression",
    "taskType": "BOTH",
    "version": "1.0",
    "provider": "notebook",
    "description": "Classifier trained from models(notebook)/final_df.csv.",
    "creditCost": 1,
    "artifactKey": "logistic-regression"
  },
  "repository": null,
  "pullRequest": null,
  "mergeProbability": 78.5,
  "qualityScore": 78.5,
  "qualityLabel": "Good",
  "recommendation": "Looks ready for review. Keep the existing tests and ask a reviewer to verify the edge cases.",
  "factors": [
    {
      "name": "Change size",
      "description": "4 files and 175 changed lines were considered.",
      "impact": "POSITIVE",
      "order": 0
    },
    {
      "name": "Repository context",
      "description": "The notebook model used Python and fix as categorical features.",
      "impact": "NEUTRAL",
      "order": 1
    }
  ]
}
```

### `GET /dashboard`

Authentication: **User**.

No path/query parameters. totalPredictions counts saved predictions; averageMergeProbability averages non-null stored merge probabilities, or null if none exist. usage describes the current month. subscription is the current subscription. recentPredictions includes up to five complete predictions, newest first.

**Request body:** none.

**Response 200:**

```json
{
  "totalPredictions": 1,
  "averageMergeProbability": 78.5,
  "usage": {
    "predictionsUsed": 1,
    "creditsUsed": 1,
    "creditLimit": 5,
    "creditsRemaining": 4
  },
  "subscription": {
    "subscriptionId": "<subscriptionId>",
    "status": "ACTIVE",
    "startedAt": "2026-10-04T12:00:00",
    "plan": {
      "planId": "<planId>",
      "code": "FREE",
      "name": "Free",
      "monthlyCredits": 5,
      "description": "5 credits each month",
      "parentPlanCode": null,
      "models": [
        {
          "modelId": "<modelId>",
          "code": "model-1",
          "name": "Model 1 - Logistic Regression",
          "taskType": "BOTH",
          "version": "1.0",
          "provider": "notebook",
          "description": "Classifier trained from models(notebook)/final_df.csv.",
          "creditCost": 1,
          "artifactKey": "logistic-regression"
        }
      ]
    }
  },
  "recentPredictions": [
    {
      "predictionId": "<predictionId>",
      "status": "COMPLETED",
      "predictionType": "BOTH",
      "createdAt": "2026-10-04T12:00:00",
      "completedAt": "2026-10-04T12:00:00",
      "modelVersion": "1.0",
      "creditsCost": 1,
      "inferenceKey": "logistic-regression",
      "model": {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1 - Logistic Regression",
        "taskType": "BOTH",
        "version": "1.0",
        "provider": "notebook",
        "description": "Classifier trained from models(notebook)/final_df.csv.",
        "creditCost": 1,
        "artifactKey": "logistic-regression"
      },
      "repository": null,
      "pullRequest": null,
      "mergeProbability": 78.5,
      "qualityScore": 78.5,
      "qualityLabel": "Good",
      "recommendation": "Looks ready for review. Keep the existing tests and ask a reviewer to verify the edge cases.",
      "factors": [
        {
          "name": "Change size",
          "description": "4 files and 175 changed lines were considered.",
          "impact": "POSITIVE",
          "order": 0
        },
        {
          "name": "Repository context",
          "description": "The notebook model used Python and fix as categorical features.",
          "impact": "NEUTRAL",
          "order": 1
        }
      ]
    }
  ]
}
```

## Admin routes

Log in through /login with an admin account. The seeded username is admin; its initial password comes from ADMIN_PASSWORD (default 1234). There is no separate admin-login route.

### Model write fields

POST requires code, name, taskType, version. PATCH accepts the same fields, all optional.

| Field | Type | Create default / rules |
| --- | --- | --- |
| code | string | Required; 2–80 characters; trimmed/lowercased, unique |
| name | string | Required; 1–150 characters; trimmed, not blank |
| taskType | string | Required; BOTH, MERGE_PROBABILITY, PR_QUALITY; trimmed/uppercased |
| version | string | Required; 1–80 characters; trimmed, not blank |
| provider | string or null | null |
| description | string or null | null |
| creditCost | integer | 1; range 1–100000 |
| artifactKey | string or null | Defaults to code if absent/null/empty on create |
| active | boolean | true |

Use a classifier name or model-1 through model-6 as artifactKey. Unsupported strings can be saved but cause 503 at prediction time. On create, supply lowercase without surrounding whitespace; PATCH normalizes a nonempty value. Clearing artifactKey makes prediction use code. provider/description can be cleared with null. Omit other nonnullable fields or provide a valid value, not null.

Admin model responses extend public model objects with active (boolean), createdAt (timestamp), and retiredAt (timestamp or null). Deactivation sets retiredAt; reactivation clears it.

### Plan write fields

POST requires code, name, monthlyCredits. PATCH accepts the same fields, all optional.

| Field | Type | Create default / rules |
| --- | --- | --- |
| code | string | Required; 2–80 characters; trimmed/uppercased, unique |
| name | string | Required; 1–150 characters; trimmed, not blank |
| monthlyCredits | integer | Required; range 0–1000000000 |
| parentPlanCode | string or null | null; existing plan code, trimmed/uppercased |
| modelCodes | array of strings | []; existing model codes, trimmed/lowercased; duplicates removed |
| description | string or null | Empty string if absent/null on create |
| active | boolean | true |

modelCodes replaces the direct list; it does not append. On PATCH, [] or null clears direct models. Null/empty parentPlanCode clears inheritance. Omit other fields to keep them; use an empty description string to clear it on PATCH.

Admin plan responses extend public plans with active and directModels. directModels contains explicitly assigned public model objects; models contains the combined inherited/direct objects. An inactive parent still contributes models. Actual model activity is enforced by /models and /predict.

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
    "name": "Model 1 - Logistic Regression",
    "taskType": "BOTH",
    "version": "1.0",
    "provider": "notebook",
    "description": "Classifier trained from models(notebook)/final_df.csv.",
    "creditCost": 1,
    "artifactKey": "logistic-regression",
    "active": true,
    "createdAt": "2026-10-04T12:00:00",
    "retiredAt": null
  }
]
```

### `POST /admin/api/models`

Authentication: **Admin**.

Creates a catalog record using the model write fields above. Assign it to a plan before users can select it. Duplicate code: 409. Blank code/name/version or invalid taskType: 400. Invalid schema length/range: 422.

**Request body:**

```json
{
  "code": "student-model",
  "name": "Student Model",
  "taskType": "BOTH",
  "version": "1.0",
  "provider": "notebook",
  "description": "Logistic regression for the student plan.",
  "creditCost": 2,
  "artifactKey": "logistic-regression",
  "active": true
}
```

**Response 201:**

```json
{
  "modelId": "<modelId>",
  "code": "student-model",
  "name": "Student Model",
  "taskType": "BOTH",
  "version": "1.0",
  "provider": "notebook",
  "description": "Logistic regression for the student plan.",
  "creditCost": 2,
  "artifactKey": "logistic-regression",
  "active": true,
  "createdAt": "2026-10-04T12:00:00",
  "retiredAt": null
}
```

### `PATCH /admin/api/models/{modelId}`

Authentication: **Admin**.

Required path modelId: database UUID, not model code. Changes only included fields. Unknown ID: 404. Duplicate code: 409. Blank code/name/version or invalid taskType: 400. Cost changes apply to future predictions; past creditsCost stays unchanged.

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
  "taskType": "BOTH",
  "version": "1.0",
  "provider": "notebook",
  "description": "Logistic regression for the student plan.",
  "creditCost": 3,
  "artifactKey": "logistic-regression",
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
    "taskType": "BOTH",
    "version": "1.0",
    "provider": "notebook",
    "description": "Logistic regression for the student plan.",
    "creditCost": 3,
    "artifactKey": "logistic-regression",
    "active": false,
    "createdAt": "2026-10-04T12:00:00",
    "retiredAt": "2026-10-04T12:00:00"
  }
}
```

### `GET /admin/api/plans`

Authentication: **Admin**.

No path/query parameters. All plans, including inactive ones, ordered by monthlyCredits.

**Request body:** none.

**Response 200:** Array example shows one complete item; all matching items are returned. Empty results use `[]`.

```json
[
  {
    "planId": "<planId>",
    "code": "FREE",
    "name": "Free",
    "monthlyCredits": 5,
    "description": "5 credits each month",
    "active": true,
    "parentPlanCode": null,
    "directModels": [
      {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1 - Logistic Regression",
        "taskType": "BOTH",
        "version": "1.0",
        "provider": "notebook",
        "description": "Classifier trained from models(notebook)/final_df.csv.",
        "creditCost": 1,
        "artifactKey": "logistic-regression"
      }
    ],
    "models": [
      {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1 - Logistic Regression",
        "taskType": "BOTH",
        "version": "1.0",
        "provider": "notebook",
        "description": "Classifier trained from models(notebook)/final_df.csv.",
        "creditCost": 1,
        "artifactKey": "logistic-regression"
      }
    ]
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
  "monthlyCredits": 20,
  "parentPlanCode": null,
  "modelCodes": [
    "model-1"
  ],
  "description": "20 credits each month",
  "active": true
}
```

**Response 201:**

```json
{
  "planId": "<planId>",
  "code": "STUDENT",
  "name": "Student",
  "monthlyCredits": 20,
  "description": "20 credits each month",
  "active": true,
  "parentPlanCode": null,
  "directModels": [
    {
      "modelId": "<modelId>",
      "code": "model-1",
      "name": "Model 1 - Logistic Regression",
      "taskType": "BOTH",
      "version": "1.0",
      "provider": "notebook",
      "description": "Classifier trained from models(notebook)/final_df.csv.",
      "creditCost": 1,
      "artifactKey": "logistic-regression"
    }
  ],
  "models": [
    {
      "modelId": "<modelId>",
      "code": "model-1",
      "name": "Model 1 - Logistic Regression",
      "taskType": "BOTH",
      "version": "1.0",
      "provider": "notebook",
      "description": "Classifier trained from models(notebook)/final_df.csv.",
      "creditCost": 1,
      "artifactKey": "logistic-regression"
    }
  ]
}
```

### `PATCH /admin/api/plans/{planId}`

Authentication: **Admin**.

Required path planId: database UUID, not code. This example inherits FREE and removes direct models, so model-1 stays available through its parent. Unknown plan/parent/model: 404. Duplicate code or existing inheritance cycle: 409. Inheriting from itself or a descendant: 400 (`A plan cannot inherit from itself`). Blank name: 400. Credit changes affect current allowance without resetting usage.

**Request body:**

```json
{
  "monthlyCredits": 40,
  "parentPlanCode": "FREE",
  "modelCodes": [],
  "description": "40 credits each month"
}
```

**Response 200:**

```json
{
  "planId": "<planId>",
  "code": "STUDENT",
  "name": "Student",
  "monthlyCredits": 40,
  "description": "40 credits each month",
  "active": true,
  "parentPlanCode": "FREE",
  "directModels": [],
  "models": [
    {
      "modelId": "<modelId>",
      "code": "model-1",
      "name": "Model 1 - Logistic Regression",
      "taskType": "BOTH",
      "version": "1.0",
      "provider": "notebook",
      "description": "Classifier trained from models(notebook)/final_df.csv.",
      "creditCost": 1,
      "artifactKey": "logistic-regression"
    }
  ]
}
```

### `DELETE /admin/api/plans/{planId}`

Authentication: **Admin**.

Required path planId: database UUID. No query parameters. Sets active=false; unknown ID returns 404. Deleting FREE returns 400: `The FREE plan cannot be deleted`. Inactive plans disappear from /plans and cannot be newly selected. Existing subscriptions are not cancelled/migrated. Reactivate with PATCH and {"active": true}.

**Request body:** none.

**Response 200:**

```json
{
  "message": "Plan deactivated",
  "plan": {
    "planId": "<planId>",
    "code": "STUDENT",
    "name": "Student",
    "monthlyCredits": 40,
    "description": "40 credits each month",
    "active": false,
    "parentPlanCode": "FREE",
    "directModels": [],
    "models": [
      {
        "modelId": "<modelId>",
        "code": "model-1",
        "name": "Model 1 - Logistic Regression",
        "taskType": "BOTH",
        "version": "1.0",
        "provider": "notebook",
        "description": "Classifier trained from models(notebook)/final_df.csv.",
        "creditCost": 1,
        "artifactKey": "logistic-regression"
      }
    ]
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
    "predictionType": "BOTH",
    "createdAt": "2026-10-04T12:00:00"
  }
]
```

## Browser pages

| Route | Authentication | Request data | Response |
| --- | --- | --- | --- |
| `GET /admin/` | Public page; data requires Admin | None | 200 text/html admin console |
| `GET /admin/admin.css` | Public | None | CSS asset |
| `GET /admin/admin.js` | Public | None | JavaScript asset |
| `GET /docs` | Public | None | 200 text/html Swagger UI |
| `GET /redoc` | Public | None | 200 text/html ReDoc UI |
| `GET /openapi.json` | Public | None | 200 application/json generated schema |

The admin page signs in through /login and calls /admin/api/*. When opened through a separate static server (for example VS Code Live Server), its api-base meta tag defaults to http://127.0.0.1:8000. Start the backend before signing in.

OpenAPI describes request validation. Many handlers return plain dictionaries without response models, so this document supplies the response examples.

## Client example

1. Register or log in; store accessToken.
2. Send the bearer header on protected calls.
3. GET /active-plan to display credits and GET /models to show available models/costs.
4. POST /predict with manual features or a GitHub PR URL.
5. Refresh /active-plan after success; use /history and /predictions/{predictionId} for saved results.
6. Use GET /plans and POST /subscription to switch plans.

PowerShell example with an existing account:

```powershell
$apiBase = "http://127.0.0.1:8000"
$loginBody = @{ username = "sam"; password = "pass1234" } | ConvertTo-Json
$session = Invoke-RestMethod -Method Post -Uri "$apiBase/login" -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($session.accessToken)" }
Invoke-RestMethod -Uri "$apiBase/active-plan" -Headers $headers
$predictionBody = @{
    inputType = "MANUAL_FEATURES"
    predictionType = "BOTH"
    modelId = "model-1"
    features = @{ additions = 150; deletions = 25; changedFiles = 4; language = "Python" }
} | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post -Uri "$apiBase/predict" -Headers $headers -ContentType "application/json" -Body $predictionBody
```

The account must exist, have model-1 access, and have enough credits. Use the error table to handle unsuccessful responses.
