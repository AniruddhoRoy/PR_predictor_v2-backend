# Entity Relationship Diagram

Matches the 9 tables, 104 columns, and 11 foreign keys declared in [models.py](models.py), including the `plan_model_access` association table.

`PK` = primary key, `FK` = foreign key, `UK` = unique key. Fields marked `nullable` may be null; all other fields are required. Solid links include the parent key in the child primary key; dotted links use a separate child key. Exact SQL types and indexes are listed in [SCHEMA_DIAGRAM.md](SCHEMA_DIAGRAM.md).

```mermaid
erDiagram
    USERS ||--o| USER_SETTINGS : has
    USERS ||..o{ SUBSCRIPTIONS : owns
    PLANS ||..o{ SUBSCRIPTIONS : defines
    PLANS ||--o{ PLAN_MODEL_ACCESS : grants
    MODELS ||--o{ PLAN_MODEL_ACCESS : included_in
    USERS ||..o{ USAGE_PERIODS : tracks
    USERS ||..o{ PREDICTIONS : submits
    USAGE_PERIODS ||..o{ PREDICTIONS : accounts_for
    MODELS ||..o{ PREDICTIONS : prices
    PREDICTIONS ||..o| PREDICTION_RESULTS : has_result
    USERS ||..o{ PREDICTION_RESULTS : owns_results

    USERS {
        string user_id PK
        string username UK
        string email UK
        string password_hash
        string full_name
        string role "USER or ADMIN; checked by the application"
        text github_profile_url "nullable"
        datetime created_at
        datetime updated_at
    }

    USER_SETTINGS {
        string user_id PK, FK
        string theme_mode
        boolean notifications_enabled
        string default_prediction_type
        string default_input_mode
        datetime updated_at
    }

    PLANS {
        string plan_id PK
        string code UK
        string name
        integer credits "credit allowance"
        integer duration "duration in days"
        text description
        boolean active
    }

    PLAN_MODEL_ACCESS {
        string plan_id PK, FK
        string model_id PK, FK
    }

    MODELS {
        string model_id PK
        string code UK
        string name
        string version
        string provider
        text description "nullable"
        integer credit_cost "credits per successful prediction"
        boolean active
        datetime created_at
        datetime retired_at "nullable"
    }

    SUBSCRIPTIONS {
        string subscription_id PK
        string user_id FK
        string plan_id FK
        string status
        datetime started_at
        datetime ended_at "required subscription end time"
        datetime created_at
    }

    USAGE_PERIODS {
        string usage_period_id PK
        string user_id FK
        date time_stamp "date used for credit tracking"
        integer credits_used
    }

    PREDICTIONS {
        string prediction_id PK
        string user_id FK
        string usage_period_id FK
        string model_id FK
        text pr_url
        string status "COMPLETED or FAILED"
        integer credits_cost "actual charge; zero on analyzer failure"
        datetime created_at
        datetime completed_at "nullable"
        integer http_status "nullable; analyzer status or mapped service error"
        text error_message "nullable"
    }

    PREDICTION_RESULTS {
        string result_id PK
        string prediction_id FK, UK
        string user_id FK
        text pr_url
        string repository "owner/repository text; not a foreign key"
        integer pr_number
        text title
        text description "nullable"
        string author "nullable"
        string author_association "nullable"
        string state "nullable"
        boolean merged "nullable"
        boolean draft "nullable"
        boolean mergeable "nullable"
        string mergeable_state "nullable"
        datetime pr_created_at "nullable; DateTime with timezone=True"
        datetime pr_updated_at "nullable; DateTime with timezone=True"
        string head_sha "nullable"
        string base_branch "nullable"
        integer additions "nullable"
        integer deletions "nullable"
        integer changed_files "nullable"
        integer commit_count "nullable"
        integer comment_count "nullable"
        integer review_comment_count "nullable"
        integer review_count "nullable"
        integer approvals "nullable"
        integer changes_requested "nullable"
        json labels "nullable"
        json files "nullable"
        json comments "nullable"
        json reviews "nullable"
        json review_comments "nullable"
        json commits "nullable"
        json checks "nullable"
        json statuses "nullable"
        json warnings "nullable"
        decimal merge_probability "nullable"
        decimal quality_score "nullable"
        string quality "nullable"
        string confidence "nullable"
        text summary "nullable"
        text merge_reasoning "nullable"
        json recommendations "nullable"
        json potential_improvements "nullable"
        json limitations "nullable"
        text probability_note "nullable"
        datetime generated_at
    }
```

## How the relationships are used

- **Users:** settings are optional one-to-one through `user_settings.user_id`. Users can have multiple subscriptions, usage records, predictions, and prediction results. Admin access comes from `users.role`.
- **Plans and models:** plans grant access directly through `plan_model_access`. Each plan has `credits` and a `duration` in days. There is no parent-plan relationship.
- **Subscriptions and usage:** `ended_at` is required. The application sets it from the start time and plan duration. Usage lookup uses the user and the subscription start date; `time_stamp` is a DATE. The database does not enforce uniqueness on that pair or link usage directly to a subscription.
- **Predictions:** each prediction belongs to a user, a usage record, and a model. The PR URL is stored directly on the prediction. Analyzer failures are saved with `status = FAILED`, `http_status`, `error_message`, and zero credits charged.
- **Results:** a prediction can have at most one result because `prediction_results.prediction_id` is unique. Successful analysis creates a result; failures do not. Results also have a direct foreign key to the user.
- **Analyzer data:** PR metadata is stored in result columns; feature lists and recommendations use JSON columns. Scores, quality, confidence, summary, reasoning, and the probability note are also stored on the result. There is no `analysis_response` column.

There are no current models for repositories, pull requests, prediction inputs, prediction features, or prediction factors. Repository and PR details belong to `prediction_results`. `/predict-dev` does not save predictions or charge credits.
