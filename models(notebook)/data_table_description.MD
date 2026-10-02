## These tables are derived from the GitHub REST API. Refer to the [GitHub API documentation](https://docs.github.com/en/rest) for more details, and the endpoint notes below for each dataset.

### source [link](https://huggingface.co/datasets/hao-li/AIDev/blob/main/data_table.md)

## `repository`

- **Endpoint**: `GET /repos/{owner}/{repo}`
- **Derivation**: Repository metadata fetched per scoped project and flattened into a tabular row for each repository.
  | Column | Description | GitHub field |
  | --- | --- | --- |
  | `id` | Numeric repository identifier. | `id` |
  | `url` | API URL for the repository. | `url` |
  | `license` | SPDX identifier for the repository license, when present. | `license.spdx_id` |
  | `full_name` | Owner/name slug for the repository. | `full_name` |
  | `language` | Primary language reported by GitHub's linguist. | `language` |
  | `forks` | Count of repository forks. | `forks_count` |
  | `stars` | Stargazer count. | `stargazers_count` |

## `user`

- **Endpoint**: `GET /users/{username}`
- **Derivation**: Profile documents for scoped contributors flattened into one row per GitHub user.
  | Column | Description | GitHub field |
  | --- | --- | --- |
  | `id` | Unique numeric user identifier. | `id` |
  | `login` | Username (login). | `login` |
  | `followers` | Total followers the account has. | `followers` |
  | `following` | Count of accounts the user follows. | `following` |
  | `created_at` | Account creation timestamp. | `created_at` |

## `pull_request`

- **Endpoint**: `GET /search/issues` (Issues Search API) scoped to pull requests
- **Derivation**: Search results for each coding agent.
  | Column | Description | GitHub field |
  | --- | --- | --- |
  | `id` | Pull request identifier. | `id` |
  | `number` | Repository-local pull request number. | `number` |
  | `title` | Title string. | `title` |
  | `body` | Markdown body submitted with the PR. | `body` |
  | `agent` | Mining label for the coding agent, added during aggregation. | _(derived)_ |
  | `user_id` | Numeric identifier for the author. | `user.id` |
  | `user` | Login name of the author. | `user.login` |
  | `state` | Open/closed state reported by the API. | `state` |
  | `created_at` | Creation timestamp. | `created_at` |
  | `closed_at` | Closure timestamp when available. | `closed_at` |
  | `merged_at` | Merge timestamp taken from the embedded `pull_request` object when present. | `pull_request.merged_at` |
  | `repo_id` | Foreign key to the repository table, joined via metadata. | _(derived from repository metadata)_ |
  | `repo_url` | API URL of the repository containing the PR. | `repository_url` or inferred from PR URL |
  | `html_url` | Web URL for the PR. | `html_url` |

## `pr_comments`

- **Endpoint**: `GET /repos/{owner}/{repo}/issues/{issue_number}/comments`
- **Derivation**: Issue-thread comments joined back to the parent pull request identifier from the file context.
  | Column | Description | GitHub field |
  | --- | --- | --- |
  | `id` | Comment identifier. | `id` |
  | `pr_id` | Associated pull request ID, derived from the filename. | _(derived)_ |
  | `user` | Comment author's login. | `user.login` |
  | `user_id` | Comment author's numeric ID. | `user.id` |
  | `user_type` | Actor type (e.g., `User`, `Bot`). | `user.type` |
  | `created_at` | Comment creation timestamp. | `created_at` |
  | `body` | Comment Markdown body. | `body` |

## `pr_reviews`

- **Endpoint**: `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews`
- **Derivation**: Review payloads flattened with the pull request identifier derived from the captured filename metadata.
  | Column | Description | GitHub field |
  | --- | --- | --- |
  | `id` | Review identifier. | `id` |
  | `pr_id` | Parent pull request ID, from the scoped filename. | _(derived)_ |
  | `user` | Reviewer login when available. | `user.login` |
  | `user_type` | Reviewer account type. | `user.type` |
  | `state` | Review state (e.g., `APPROVED`, `CHANGES_REQUESTED`). | `state` |
  | `submitted_at` | Timestamp the review was submitted. | `submitted_at` |
  | `body` | Top-level review comment body. | `body` |

## `pr_review_comments`

- **Endpoint**: `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}/comments`
- **Derivation**: Inline review discussion rows expanded so each comment is linked to its owning review and pull request.
  | Column | Description | GitHub field |
  | --- | --- | --- |
  | `id` | Inline review comment identifier. | `id` |
  | `pull_request_review_id` | Review that owns the comment. | `pull_request_review_id` |
  | `user` | Commenter login. | `user.login` |
  | `user_type` | Commenter type. | `user.type` |
  | `diff_hunk` | Contextual diff snippet provided by GitHub. | `diff_hunk` |
  | `path` | File path relative to the repository root. | `path` |
  | `position` | Position of the comment in the diff. | `position` |
  | `original_position` | Original diff position before updates. | `original_position` |
  | `commit_id` | SHA of the head commit when the comment was made. | `commit_id` |
  | `original_commit_id` | SHA of the commit when the comment was originally posted. | `original_commit_id` |
  | `body` | Markdown content of the inline comment. | `body` |
  | `pull_request_url` | API URL of the PR. | `pull_request_url` |
  | `created_at` | Creation timestamp. | `created_at` |
  | `updated_at` | Last update timestamp. | `updated_at` |
  | `in_reply_to_id` | Parent inline comment identifier when this is part of a thread. | `in_reply_to_id` |

## `pr_commits`

- **Endpoint**: `GET /repos/{owner}/{repo}/pulls/{pull_number}/commits`
- **Derivation**: Commit summaries retrieved for each pull request and associated with the scoped pull request identifier.
  | Column | Description | GitHub field |
  | --- | --- | --- |
  | `sha` | Commit SHA. | `sha` |
  | `pr_id` | Parent PR identifier (derived from filename). | _(derived)_ |
  | `author` | Commit author login or author name when the login is absent. | `author.login` or `commit.author.name` |
  | `committer` | Commit committer login or committer name when absent. | `committer.login` or `commit.committer.name` |
  | `message` | Commit message subject and body. | `commit.message` |

## `pr_commit_details`

- **Endpoint**: `GET /repos/{owner}/{repo}/commits/{sha}`
- **Derivation**: Commit detail payloads expanded to include stats and per-file information tied back to the pull request context.
  | Column | Description | GitHub field |
  | --- | --- | --- |
  | `sha` | Commit SHA. | `sha` |
  | `pr_id` | Owning PR identifier. | _(derived)_ |
  | `author` | Author login or name. | `author.login` or `commit.author.name` |
  | `committer` | Committer login or name. | `committer.login` or `commit.committer.name` |
  | `message` | Commit message. | `commit.message` |
  | `commit_stats_total` | Total lines touched. | `stats.total` |
  | `commit_stats_additions` | Lines added. | `stats.additions` |
  | `commit_stats_deletions` | Lines removed. | `stats.deletions` |
  | `filename` | Path of the changed file (one row per file; null when no file list). | `files[].filename` |
  | `status` | File change status (added, modified, etc.). | `files[].status` |
  | `additions` | Lines added in the file. | `files[].additions` |
  | `deletions` | Lines deleted in the file. | `files[].deletions` |
  | `changes` | Total changes in the file. | `files[].changes` |
  | `patch` | Unified diff provided by the API (masked when licences forbid redistribution). | `files[].patch` |

## `pr_timeline`

- **Endpoint**: `GET /repos/{owner}/{repo}/issues/{issue_number}/timeline`
- **Derivation**: Timeline events for each pull request unfolded into one row per event with actor and timestamp metadata.
  | Column | Description | GitHub field |
  | --- | --- | --- |
  | `pr_id` | Identifier of the PR whose timeline was fetched. | _(derived)_ |
  | `event` | Event type string (e.g., `labeled`, `referenced`, `committed`). | `event` |
  | `commit_id` | SHA associated with commit-style events. | `commit_id` or `sha` |
  | `created_at` | Timestamp when the event occurred. | `created_at` |
  | `actor` | Login of the actor triggering the event. | `actor.login` |
  | `assignee` | Login of the assignee added or removed (when applicable). | `assignee.login` |
  | `label` | Name of the label involved in label events. | `label.name` |
  | `message` | Message content for comment, system, or cross-reference events. | Event-specific fields such as `body` or `message` |

## `issue`

- **Endpoint**: `GET /repos/{owner}/{repo}/issues/{issue_number}`
- **Derivation**: Referenced issues fetched for scoped pull requests and flattened into one row per issue.
  | Column | Description | GitHub field |
  | --- | --- | --- |
  | `id` | Issue identifier. | `id` |
  | `number` | Repository-local issue number. | `number` |
  | `title` | Issue title. | `title` |
  | `body` | Markdown body of the issue. | `body` |
  | `user` | Issue author's login. | `user.login` |
  | `state` | Issue state (`open`, `closed`). | `state` |
  | `created_at` | Issue creation timestamp. | `created_at` |
  | `closed_at` | Issue closure timestamp when available. | `closed_at` |
  | `html_url` | Web URL for the issue. | `html_url` |

## `related_issue`

- **Endpoint**: Combines data from the pull request timeline (`GET /repos/{owner}/{repo}/issues/{issue_number}/timeline`) and issue bodies
- **Derivation**: Cross-references detected between pull requests and issues using timeline events and body hyperlinks.
  | Column | Description | Provenance |
  | --- | --- | --- |
  | `pr_id` | Identifier of the referencing PR. | Scoped PR metadata |
  | `issue_id` | Numeric ID of the referenced issue, joined from mined issues. | `issues.json` payloads |
  | `source` | Whether the relationship came from the PR `body` or the `timeline`. | Derived during parsing |

## `pr_task_type`

- **Endpoint**: Derived from pull request metadata mined via the endpoints above
- **Derivation**: LLM classification applied to the pull request titles and commit messages to assign a task type.
  | Column | Description |
  | --- | --- |
  | `agent` | Coding agent for the PR. |
  | `id` | Pull request identifier aligned with other tables. |
  | `title` | PR title supplied to the classifier. |
  | `reason` | Model-provided explanation supporting the assigned task type. |
  | `type` | Conventional-commit style category (e.g., `feat`, `fix`, `docs`). |

## Aggregated tables

- **Endpoint**: Aggregates the same REST responses listed for `repository`, `user`, and `pull_request`
- **Derivation**: Union of scoped tables across all coding agents, preserving the original column semantics.
  | Table | Notes |
  | --- | --- |
  | `all_user` | Reuses the columns and GitHub sources listed above for users but aggregates across all agents. |
  | `all_repository` | Reuses the repository columns and sources above across all agents. |
  | `all_pull_request` | Reuses the pull request columns and sources above across all agents. |
