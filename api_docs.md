# PR Predictor API

Base URL: `http://127.0.0.1:8000`

The prediction API needs one thing from the caller: a GitHub pull request URL. The server reads the PR from GitHub, extracts model features, runs the selected notebook model, saves the prediction, and returns the scores.

## Authentication

Register or log in first:

```http
POST /register
Content-Type: application/json

{"username":"sam","email":"sam@example.com","password":"pass1234","fullName":"Sam"}
```

```http
POST /login
Content-Type: application/json

{"username":"sam","password":"pass1234"}
```

Use the returned token on protected routes:

```http
Authorization: Bearer <accessToken>
```

## Python prediction helper

`prediction_engine.predict(pull_request_url, model_key="model-1")` also accepts the same GitHub PR URL directly. It fetches the URL features and returns `(merge_probability, quality_score, factors)`.

## `POST /predict-dev`

Development-only route. It does not require a bearer token, user, plan, subscription, or credits, and it does not save a prediction. Remove this route before deployment.

It accepts the same request as `/predict`:

```json
{
  "pullRequestUrl": "https://github.com/owner/repository/pull/123",
  "predictionType": "BOTH",
  "modelId": "model-1"
}
```

`modelId` is optional and defaults to `model-1`. Use a model code (`model-1` through `model-6`) or classifier name. A model UUID from the protected catalog is not needed for this route.

The response contains `status`, `predictionType`, `modelId`, `repository`, `pullRequest`, `features`, `mergeProbability`, `qualityScore`, `qualityLabel`, `recommendation`, and `factors`. It has no `predictionId` because nothing is saved.

## `POST /predict`

Authentication: user token.

### Request

The smallest request is a JSON object with only `pullRequestUrl`:

```json
{
  "pullRequestUrl": "https://github.com/owner/repository/pull/123"
}
```

Optional fields:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `pullRequestUrl` | string | required | Public or accessible GitHub PR URL |
| `predictionType` | string | `BOTH` | `BOTH`, `MERGE_PROBABILITY`, or `PR_QUALITY` |
| `modelId` | string | first available model | Model UUID such as `<modelId>` or seeded code such as `model-1` |

A JSON string is also accepted:

```json
"https://github.com/owner/repository/pull/123"
```

Manual feature input is not supported. `inputType`, `features`, and other unknown request fields are rejected.

### What GitHub data is read

The backend calls these GitHub REST endpoints:

- `GET /repos/{owner}/{repo}/pulls/{number}`
- `GET /repos/{owner}/{repo}`
- `GET /repos/{owner}/{repo}/pulls/{number}/files`

For private repositories or higher GitHub limits, set `GITHUB_TOKEN` in the server environment. The token is never sent by the client.

### Features sent to the model

The response and saved prediction contain these derived features:

| Feature | Source |
| --- | --- |
| `title_word_count` | PR title word count |
| `body_word_count` | PR body word count |
| `total_lines_added` | GitHub PR `additions` |
| `total_lines_deleted` | GitHub PR `deletions` |
| `total_lines_changed` | additions + deletions |
| `total_files_touched` | GitHub PR `changed_files` |
| `files_added` | Changed files with status `added` |
| `files_modified` | Changed files with status `modified` |
| `files_deleted` | Changed files with status `removed` |
| `total_commits` | GitHub PR `commits` |
| `stars` | Repository `stargazers_count` |
| `forks` | Repository `forks_count` |
| `language` | Repository `language`, or `unknown` |
| `agent` | Small title/branch heuristic, or `unknown` |
| `task_type` | Conventional title prefix such as `fix` or `feat`, or `unknown` |

### Successful response: `200`

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
    "creditCost": 1,
    "artifactKey": "logistic-regression"
  },
  "repository": {
    "owner": "owner",
    "name": "repository",
    "url": "https://github.com/owner/repository"
  },
  "pullRequest": {
    "number": 123,
    "url": "https://github.com/owner/repository/pull/123",
    "title": "Fix login validation",
    "state": "OPEN",
    "authorLogin": "sam"
  },
  "features": {
    "title_word_count": 3,
    "body_word_count": 18,
    "total_lines_added": 42,
    "total_lines_deleted": 10,
    "total_lines_changed": 52,
    "total_files_touched": 4,
    "files_added": 1,
    "files_modified": 3,
    "files_deleted": 0,
    "total_commits": 2,
    "stars": 100,
    "forks": 20,
    "language": "Python",
    "agent": "unknown",
    "task_type": "fix"
  },
  "mergeProbability": 78.5,
  "qualityScore": 78.5,
  "qualityLabel": "Good",
  "recommendation": "Looks ready for review. Keep the existing tests and ask a reviewer to verify the edge cases.",
  "factors": [
    {
      "name": "Change size",
      "description": "4 files and 52 changed lines were considered.",
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

`mergeProbability` and `qualityScore` are percentages from 0 to 100. `qualityScore` currently reuses the merge model score because the notebook has one merge classifier. For `MERGE_PROBABILITY`, `qualityScore` is `null`; for `PR_QUALITY`, `mergeProbability` is `null`.

The first request for a model trains it from `models(notebook)/final_df.csv` if no saved model exists, so it may take longer. A successful request charges the model's `creditCost` once. GitHub or model failures do not charge credits.

## Errors

Errors use this shape:

```json
{"detail":"message"}
```

| Status | Meaning |
| --- | --- |
| `400` | Invalid PR URL or prediction type |
| `401` | Missing or invalid bearer token |
| `403` | Model is not included in the active plan |
| `404` | GitHub PR/repository or model was not found |
| `422` | Invalid request body or PR has more than 3000 changed files |
| `429` | Monthly credits or GitHub rate limit is exhausted |
| `502` | GitHub returned incomplete data or is unavailable |
| `503` | Model is unavailable; no credits were charged |

## Other useful routes

- `GET /health` — returns `{ "status": "ok" }`.
- `GET /models` — lists models available to the signed-in user's plan.
- `GET /active-plan` — shows credits used and remaining.
- `GET /history` or `GET /predictions` — lists the user's saved predictions.
- `GET /predictions/{predictionId}` — returns one saved prediction.

Interactive OpenAPI documentation is available at `/docs`.
