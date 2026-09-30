# Entity Relationship Diagram

This backend uses the frontend design as its source and adds a simple authorization role to `users`. `role` is `USER` for normal accounts and `ADMIN` for the browser admin console. Registration can only create `USER`; an existing admin can promote a user.

```mermaid
erDiagram
    USERS ||--|| USER_SETTINGS : has
    USERS ||--o{ SUBSCRIPTIONS : owns
    PLANS ||--o{ SUBSCRIPTIONS : defines
    USERS ||--o{ USAGE_PERIODS : tracks
    MODELS ||--o{ PREDICTIONS : runs
    USERS ||--o{ PREDICTIONS : submits
    USAGE_PERIODS ||--o{ PREDICTIONS : counts
    REPOSITORIES ||--o{ PULL_REQUESTS : contains
    PULL_REQUESTS o|--o{ PREDICTIONS : analyzes
    PREDICTIONS ||--|| PREDICTION_INPUTS : keeps
    PREDICTIONS ||--o{ PREDICTION_FEATURES : stores
    PREDICTIONS ||--o| PREDICTION_RESULTS : produces
    PREDICTION_RESULTS ||--o{ PREDICTION_FACTORS : explains

    USERS {
        string user_id PK
        string username UK
        string email UK
        string password_hash
        string full_name
        string role "USER or ADMIN"
        string github_profile_url
        datetime created_at
        datetime updated_at
    }
    USER_SETTINGS { string user_id PK/FK string theme_mode boolean notifications_enabled string default_prediction_type string default_input_mode }
    PLANS { string plan_id PK string code UK string name integer monthly_prediction_limit boolean active }
    SUBSCRIPTIONS { string subscription_id PK string user_id FK string plan_id FK string status datetime started_at datetime ended_at }
    USAGE_PERIODS { string usage_period_id PK string user_id FK date period_start date period_end integer predictions_used integer limit_snapshot }
    MODELS { string model_id PK string code UK string name string task_type string version boolean active }
    REPOSITORIES { string repository_id PK string provider string owner string name string canonical_url }
    PULL_REQUESTS { string pull_request_id PK string repository_id FK integer number string url string title string state }
    PREDICTIONS { string prediction_id PK string user_id FK string usage_period_id FK string model_id FK string pull_request_id FK string prediction_type string status string model_version }
    PREDICTION_INPUTS { string prediction_id PK/FK string input_mode string github_url string raw_feature_text }
    PREDICTION_FEATURES { string feature_id PK string prediction_id FK string feature_name string value_type string value_text decimal value_number boolean value_boolean }
    PREDICTION_RESULTS { string result_id PK string prediction_id UK/FK decimal merge_probability decimal quality_score string quality_label string recommendation }
    PREDICTION_FACTORS { string factor_id PK string result_id FK string factor_name string description string impact integer display_order }
```

The admin console is an authorization capability over `USERS`, `PREDICTIONS`, `MODELS`, and `PLANS`; it does not need a second admin table for this small project.
