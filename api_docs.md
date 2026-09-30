# API documentation

Base URL: `http://127.0.0.1:8000`

JSON uses the camelCase names shown below. Protected endpoints require:

```http
Authorization: Bearer <accessToken>
```

Errors use FastAPI's normal shape: `{ "detail": "safe message" }`.

## Public endpoints

### `GET /health`

Returns `{ "status": "ok" }`.

### `POST /register`

```json
{
  "username": "sam",
  "email": "sam@example.com",
  "password": "pass1234",
  "fullName": "Sam Student",
  "githubProfileUrl": "https://github.com/sam"
}
```

Returns `201` with `accessToken`, `tokenType`, and `user`. New users always have role `USER`; only an admin can promote an account.

### `POST /login`

```json
{ "username": "sam", "password": "pass1234" }
```

The username field also accepts the account email. The seeded demo admin is `admin` / `1234` unless `ADMIN_PASSWORD` was set before the database was created.

## Profile, settings, and subscription

- `GET /me` or `GET /profile` returns the current user.
- `PATCH /profile` accepts `fullName`, `email`, and `githubProfileUrl`.
- `GET /settings` returns `themeMode`, `notificationsEnabled`, `defaultPredictionType`, and `defaultInputMode`.
- `PATCH /settings` accepts those same fields. Valid values are `LIGHT`/`DARK`, `MERGE_PROBABILITY`/`PR_QUALITY`/`BOTH`, and `GITHUB_URL`/`MANUAL_FEATURES`.
- `GET /subscription` returns the active plan and monthly limit.
- `POST /subscription` accepts `{ "planCode": "PREMIUM" }` or `{ "planCode": "FREE" }`. This is a local demo plan switch; it does not charge money.

## Models and predictions

### `GET /models?predictionType=BOTH`

Returns active model records. The default seeded model has code `merge-probability-v1`, task type `BOTH`, and version `1.0`.

### `POST /predict`

A prediction is synchronous. It is saved to the database before the result is returned. Free accounts can submit five predictions per calendar month; Premium is unlimited.

GitHub URL input:

```json
{
  "inputType": "GITHUB_URL",
  "predictionType": "BOTH",
  "modelId": "merge-probability-v1",
  "pullRequestUrl": "https://github.com/openai/example/pull/12"
}
```

Manual input:

```json
{
  "inputType": "MANUAL_FEATURES",
  "predictionType": "MERGE_PROBABILITY",
  "features": {
    "changedFiles": 12,
    "additions": 150,
    "deletions": 25,
    "testsAdded": true
  }
}
```

`modelId` may be omitted. It accepts either a model UUID or model code. `predictionType` controls which score is populated; `BOTH` returns both scores. A successful response includes:

```json
{
  "predictionId": "uuid",
  "status": "COMPLETED",
  "predictionType": "BOTH",
  "modelVersion": "1.0",
  "model": { "modelId": "uuid", "code": "merge-probability-v1", "name": "PR Predictor Demo", "taskType": "BOTH", "version": "1.0" },
  "repository": { "owner": "openai", "name": "example", "url": "https://github.com/openai/example" },
  "pullRequest": { "number": 12, "url": "https://github.com/openai/example/pull/12", "title": "Pull request #12", "state": "OPEN", "authorLogin": "openai" },
  "mergeProbability": 78.5,
  "qualityScore": 81.2,
  "qualityLabel": "Excellent",
  "recommendation": "Looks ready for review...",
  "factors": [{ "name": "Change size", "description": "...", "impact": "POSITIVE", "order": 0 }]
}
```

For a manual prediction `repository` and `pullRequest` are `null`.

### `GET /history?search=example&limit=20` and `GET /predictions`

Returns the current user's newest predictions. Search matches stored pull-request URL or title.

### `GET /predictions/{predictionId}`

Returns one prediction owned by the current user.

### `GET /dashboard`

Returns total predictions, average merge probability, current usage, active subscription, and five recent predictions.

## Admin API and web page

Open `GET /admin/` in a browser. The page logs in through `/login`, stores the short-lived bearer token in browser local storage, and calls:

- `GET /admin/api/stats` for user, prediction, model, and plan counts.
- `GET /admin/api/users` for the user table.
- `PATCH /admin/api/users/{userId}/role` with `{ "role": "USER" }` or `{ "role": "ADMIN" }` to promote or demote a user.
- `GET /admin/api/predictions` for the latest 100 prediction records.

All admin API calls require an authenticated `ADMIN` user and return `403` for ordinary accounts.
