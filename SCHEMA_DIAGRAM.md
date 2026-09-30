# Relational Schema Diagram

The running SQLite/MySQL schema is created by SQLAlchemy from `models.py`.

```mermaid
flowchart LR
  users["users\nPK user_id\nUQ username\nUQ email\npassword_hash\nfull_name\nrole: USER | ADMIN"]
  settings["user_settings\nPK/FK user_id\ntheme_mode\nnotifications_enabled"]
  plans["plans\nPK plan_id\nUQ code\nmonthly_prediction_limit"]
  subscriptions["subscriptions\nPK subscription_id\nFK user_id\nFK plan_id\nstatus"]
  usage["usage_periods\nPK usage_period_id\nFK user_id\nperiod_start\npredictions_used"]
  models["models\nPK model_id\nUQ code\nversion\nactive"]
  repos["repositories\nPK repository_id\nprovider/owner/name"]
  prs["pull_requests\nPK pull_request_id\nFK repository_id\nnumber/url"]
  predictions["predictions\nPK prediction_id\nFK user_id\nFK model_id\nstatus/type"]
  inputs["prediction_inputs\nPK/FK prediction_id\ninput_mode"]
  features["prediction_features\nPK feature_id\nFK prediction_id\ntyped value"]
  results["prediction_results\nPK result_id\nUQ/FK prediction_id\nscores"]
  factors["prediction_factors\nPK factor_id\nFK result_id\nimpact/order"]
  users --> settings
  users --> subscriptions
  plans --> subscriptions
  users --> usage
  usage --> predictions
  users --> predictions
  models --> predictions
  repos --> prs
  prs -. optional .-> predictions
  predictions --> inputs
  predictions --> features
  predictions --> results
  results --> factors
```

The `users.role` column is the admin option. It is constrained by application code to `USER` or `ADMIN`. Passwords are stored only as PBKDF2 hashes. A free plan has a numeric monthly limit of 5; Premium uses `NULL` for unlimited. History is a query over `predictions`, not a duplicate table.
