# API audit — 2026-10-30

Tested locally with FastAPI TestClient, a fresh SQLite database, and simulated analyzer HTTP responses. No real users, local project database, or external analyzer credits were changed. The real HTTP adapter validation and prediction storage code were exercised. Live hosting and MySQL were not tested.

Extended audit: 170/170 checks passed; 0 failed.
Application route coverage: 34 method/path combinations; untested routes: none.

Reproduce: `python tests/audit_api.py` (requires the project dependencies and httpx). Run the separate unit suite with `python -m unittest discover -s tests`.

## Confirmed failing checks

None. All seven original findings are resolved.

## Route coverage

| Method | Path | Checks |
| --- | --- | --- |
| DELETE | `/admin/api/models/{model_id}` | 5 |
| DELETE | `/admin/api/plans/{plan_id}` | 6 |
| GET | `/` | 1 |
| GET | `/active-plan` | 5 |
| GET | `/admin/api/models` | 4 |
| GET | `/admin/api/plans` | 4 |
| GET | `/admin/api/predictions` | 4 |
| GET | `/admin/api/stats` | 6 |
| GET | `/admin/api/users` | 4 |
| GET | `/dashboard` | 3 |
| GET | `/health` | 1 |
| GET | `/history` | 3 |
| GET | `/me` | 3 |
| GET | `/models` | 5 |
| GET | `/plan` | 3 |
| GET | `/plans` | 3 |
| GET | `/predictions` | 6 |
| GET | `/predictions/{prediction_id}` | 5 |
| GET | `/profile` | 3 |
| GET | `/settings` | 3 |
| GET | `/subscription` | 3 |
| PATCH | `/admin/api/models/{model_id}` | 8 |
| PATCH | `/admin/api/plans/{plan_id}` | 11 |
| PATCH | `/admin/api/users/{user_id}/role` | 7 |
| PATCH | `/profile` | 9 |
| PATCH | `/settings` | 5 |
| POST | `/admin/api/models` | 5 |
| POST | `/admin/api/plans` | 6 |
| POST | `/change-password` | 3 |
| POST | `/login` | 5 |
| POST | `/predict` | 9 |
| POST | `/predict-dev` | 1 |
| POST | `/register` | 4 |
| POST | `/subscription` | 5 |

## Full check results

| Check | Result | Evidence |
| --- | --- | --- |
| public / | PASS | GET /: expected (200,), got 200 |
| public /health | PASS | GET /health: expected (200,), got 200 |
| public /docs | PASS | GET /docs: expected (200,), got 200 |
| public /redoc | PASS | GET /redoc: expected (200,), got 200 |
| public /openapi.json | PASS | GET /openapi.json: expected (200,), got 200 |
| public /admin/ | PASS | GET /admin/: expected (200,), got 200 |
| public /admin/admin.js | PASS | GET /admin/admin.js: expected (200,), got 200 |
| public /admin/admin.css | PASS | GET /admin/admin.css: expected (200,), got 200 |
| register | PASS | POST /register: expected (201,), got 201 |
| admin login | PASS | POST /login: expected (200,), got 200 |
| missing auth POST /change-password | PASS | POST /change-password: expected (401,), got 401 |
| invalid auth POST /change-password | PASS | POST /change-password: expected (401,), got 401 |
| missing auth GET /me | PASS | GET /me: expected (401,), got 401 |
| invalid auth GET /me | PASS | GET /me: expected (401,), got 401 |
| missing auth GET /profile | PASS | GET /profile: expected (401,), got 401 |
| invalid auth GET /profile | PASS | GET /profile: expected (401,), got 401 |
| missing auth PATCH /profile | PASS | PATCH /profile: expected (401,), got 401 |
| invalid auth PATCH /profile | PASS | PATCH /profile: expected (401,), got 401 |
| missing auth GET /settings | PASS | GET /settings: expected (401,), got 401 |
| invalid auth GET /settings | PASS | GET /settings: expected (401,), got 401 |
| missing auth PATCH /settings | PASS | PATCH /settings: expected (401,), got 401 |
| invalid auth PATCH /settings | PASS | PATCH /settings: expected (401,), got 401 |
| missing auth GET /models | PASS | GET /models: expected (401,), got 401 |
| invalid auth GET /models | PASS | GET /models: expected (401,), got 401 |
| missing auth GET /subscription | PASS | GET /subscription: expected (401,), got 401 |
| invalid auth GET /subscription | PASS | GET /subscription: expected (401,), got 401 |
| missing auth GET /plan | PASS | GET /plan: expected (401,), got 401 |
| invalid auth GET /plan | PASS | GET /plan: expected (401,), got 401 |
| missing auth GET /active-plan | PASS | GET /active-plan: expected (401,), got 401 |
| invalid auth GET /active-plan | PASS | GET /active-plan: expected (401,), got 401 |
| missing auth GET /plans | PASS | GET /plans: expected (401,), got 401 |
| invalid auth GET /plans | PASS | GET /plans: expected (401,), got 401 |
| missing auth POST /subscription | PASS | POST /subscription: expected (401,), got 401 |
| invalid auth POST /subscription | PASS | POST /subscription: expected (401,), got 401 |
| missing auth POST /predict | PASS | POST /predict: expected (401,), got 401 |
| invalid auth POST /predict | PASS | POST /predict: expected (401,), got 401 |
| missing auth GET /predictions | PASS | GET /predictions: expected (401,), got 401 |
| invalid auth GET /predictions | PASS | GET /predictions: expected (401,), got 401 |
| missing auth GET /history | PASS | GET /history: expected (401,), got 401 |
| invalid auth GET /history | PASS | GET /history: expected (401,), got 401 |
| missing auth GET /predictions/missing | PASS | GET /predictions/missing: expected (401,), got 401 |
| invalid auth GET /predictions/missing | PASS | GET /predictions/missing: expected (401,), got 401 |
| missing auth GET /dashboard | PASS | GET /dashboard: expected (401,), got 401 |
| invalid auth GET /dashboard | PASS | GET /dashboard: expected (401,), got 401 |
| missing auth GET /admin/api/stats | PASS | GET /admin/api/stats: expected (401,), got 401 |
| invalid auth GET /admin/api/stats | PASS | GET /admin/api/stats: expected (401,), got 401 |
| admin authorization GET /admin/api/stats | PASS | GET /admin/api/stats: expected (403,), got 403 |
| missing auth GET /admin/api/plans | PASS | GET /admin/api/plans: expected (401,), got 401 |
| invalid auth GET /admin/api/plans | PASS | GET /admin/api/plans: expected (401,), got 401 |
| admin authorization GET /admin/api/plans | PASS | GET /admin/api/plans: expected (403,), got 403 |
| missing auth POST /admin/api/plans | PASS | POST /admin/api/plans: expected (401,), got 401 |
| invalid auth POST /admin/api/plans | PASS | POST /admin/api/plans: expected (401,), got 401 |
| admin authorization POST /admin/api/plans | PASS | POST /admin/api/plans: expected (403,), got 403 |
| missing auth PATCH /admin/api/plans/missing | PASS | PATCH /admin/api/plans/missing: expected (401,), got 401 |
| invalid auth PATCH /admin/api/plans/missing | PASS | PATCH /admin/api/plans/missing: expected (401,), got 401 |
| admin authorization PATCH /admin/api/plans/missing | PASS | PATCH /admin/api/plans/missing: expected (403,), got 403 |
| missing auth DELETE /admin/api/plans/missing | PASS | DELETE /admin/api/plans/missing: expected (401,), got 401 |
| invalid auth DELETE /admin/api/plans/missing | PASS | DELETE /admin/api/plans/missing: expected (401,), got 401 |
| admin authorization DELETE /admin/api/plans/missing | PASS | DELETE /admin/api/plans/missing: expected (403,), got 403 |
| missing auth GET /admin/api/users | PASS | GET /admin/api/users: expected (401,), got 401 |
| invalid auth GET /admin/api/users | PASS | GET /admin/api/users: expected (401,), got 401 |
| admin authorization GET /admin/api/users | PASS | GET /admin/api/users: expected (403,), got 403 |
| missing auth GET /admin/api/models | PASS | GET /admin/api/models: expected (401,), got 401 |
| invalid auth GET /admin/api/models | PASS | GET /admin/api/models: expected (401,), got 401 |
| admin authorization GET /admin/api/models | PASS | GET /admin/api/models: expected (403,), got 403 |
| missing auth POST /admin/api/models | PASS | POST /admin/api/models: expected (401,), got 401 |
| invalid auth POST /admin/api/models | PASS | POST /admin/api/models: expected (401,), got 401 |
| admin authorization POST /admin/api/models | PASS | POST /admin/api/models: expected (403,), got 403 |
| missing auth PATCH /admin/api/models/missing | PASS | PATCH /admin/api/models/missing: expected (401,), got 401 |
| invalid auth PATCH /admin/api/models/missing | PASS | PATCH /admin/api/models/missing: expected (401,), got 401 |
| admin authorization PATCH /admin/api/models/missing | PASS | PATCH /admin/api/models/missing: expected (403,), got 403 |
| missing auth DELETE /admin/api/models/missing | PASS | DELETE /admin/api/models/missing: expected (401,), got 401 |
| invalid auth DELETE /admin/api/models/missing | PASS | DELETE /admin/api/models/missing: expected (401,), got 401 |
| admin authorization DELETE /admin/api/models/missing | PASS | DELETE /admin/api/models/missing: expected (403,), got 403 |
| missing auth PATCH /admin/api/users/missing/role | PASS | PATCH /admin/api/users/missing/role: expected (401,), got 401 |
| invalid auth PATCH /admin/api/users/missing/role | PASS | PATCH /admin/api/users/missing/role: expected (401,), got 401 |
| admin authorization PATCH /admin/api/users/missing/role | PASS | PATCH /admin/api/users/missing/role: expected (403,), got 403 |
| missing auth GET /admin/api/predictions | PASS | GET /admin/api/predictions: expected (401,), got 401 |
| invalid auth GET /admin/api/predictions | PASS | GET /admin/api/predictions: expected (401,), got 401 |
| admin authorization GET /admin/api/predictions | PASS | GET /admin/api/predictions: expected (403,), got 403 |
| duplicate registration | PASS | POST /register: expected (409,), got 409 |
| invalid registration | PASS | POST /register: expected (422,), got 422 |
| wrong password | PASS | POST /login: expected (401,), got 401 |
| email login | PASS | POST /login: expected (200,), got 200 |
| user read /me | PASS | GET /me: expected (200,), got 200 |
| user read /profile | PASS | GET /profile: expected (200,), got 200 |
| user read /settings | PASS | GET /settings: expected (200,), got 200 |
| user read /models | PASS | GET /models: expected (200,), got 200 |
| user read /subscription | PASS | GET /subscription: expected (200,), got 200 |
| user read /active-plan | PASS | GET /active-plan: expected (200,), got 200 |
| user read /plan | PASS | GET /plan: expected (200,), got 200 |
| user read /plans | PASS | GET /plans: expected (200,), got 200 |
| user read /dashboard | PASS | GET /dashboard: expected (200,), got 200 |
| user read /history | PASS | GET /history: expected (200,), got 200 |
| user read /predictions | PASS | GET /predictions: expected (200,), got 200 |
| admin read /admin/api/stats | PASS | GET /admin/api/stats: expected (200,), got 200 |
| admin read /admin/api/plans | PASS | GET /admin/api/plans: expected (200,), got 200 |
| admin read /admin/api/models | PASS | GET /admin/api/models: expected (200,), got 200 |
| admin read /admin/api/users | PASS | GET /admin/api/users: expected (200,), got 200 |
| admin read /admin/api/predictions | PASS | GET /admin/api/predictions: expected (200,), got 200 |
| profile update | PASS | PATCH /profile: expected (200,), got 200 |
| duplicate profile email | PASS | PATCH /profile: expected (409,), got 409 |
| clear optional profile URL | PASS | PATCH /profile: expected (200,), got 200 |
| settings update | PASS | PATCH /settings: expected (200,), got 200 |
| invalid settings enum | PASS | PATCH /settings: expected (400,), got 400 |
| invalid model filter | PASS | GET /models?predictionType=INVALID: expected (400,), got 400 |
| create model | PASS | POST /admin/api/models: expected (201,), got 201 |
| duplicate model | PASS | POST /admin/api/models: expected (409,), got 409 |
| update model | PASS | PATCH /admin/api/models/8bc03db6-0b8d-485c-be3b-f3f13e0ab46d: expected (200,), got 200 |
| null model cost | PASS | PATCH /admin/api/models/8bc03db6-0b8d-485c-be3b-f3f13e0ab46d: expected (422,), got 422 |
| invalid model cost | PASS | PATCH /admin/api/models/8bc03db6-0b8d-485c-be3b-f3f13e0ab46d: expected (422,), got 422 |
| missing model update | PASS | PATCH /admin/api/models/missing: expected (404,), got 404 |
| missing model delete | PASS | DELETE /admin/api/models/missing: expected (404,), got 404 |
| create plan | PASS | POST /admin/api/plans: expected (201,), got 201 |
| duplicate plan | PASS | POST /admin/api/plans: expected (409,), got 409 |
| update plan | PASS | PATCH /admin/api/plans/5bc79a15-92f5-4ac8-bd26-7af38460a23c: expected (200,), got 200 |
| null plan duration | PASS | PATCH /admin/api/plans/5bc79a15-92f5-4ac8-bd26-7af38460a23c: expected (422,), got 422 |
| invalid plan duration | PASS | PATCH /admin/api/plans/5bc79a15-92f5-4ac8-bd26-7af38460a23c: expected (422,), got 422 |
| missing plan model | PASS | PATCH /admin/api/plans/5bc79a15-92f5-4ac8-bd26-7af38460a23c: expected (404,), got 404 |
| missing plan update | PASS | PATCH /admin/api/plans/missing: expected (404,), got 404 |
| missing plan delete | PASS | DELETE /admin/api/plans/missing: expected (404,), got 404 |
| available model | PASS | GET /models: expected (200,), got 200 |
| prediction disallowed model | PASS | POST /predict: expected (403,), got 403 |
| prediction missing model | PASS | POST /predict: expected (404,), got 404 |
| prediction bad URL | PASS | POST /predict: expected (422,), got 422 |
| public prediction | PASS | POST /predict-dev: expected (200,), got 200 |
| saved prediction | PASS | POST /predict: expected (200,), got 200 |
| list predictions | PASS | GET /predictions: expected (200,), got 200 |
| prediction detail | PASS | GET /predictions/9026b06d-3980-44bd-bcc4-d238720c90cb: expected (200,), got 200 |
| history/detail match | PASS | List record equals detail response |
| other user prediction denied | PASS | GET /predictions/9026b06d-3980-44bd-bcc4-d238720c90cb: expected (404,), got 404 |
| missing prediction | PASS | GET /predictions/missing: expected (404,), got 404 |
| history invalid limit | PASS | GET /predictions?limit=0: expected (422,), got 422 |
| history title search | PASS | GET /predictions?search=login: expected (200,), got 200 |
| title search matches result | PASS | Matching predictions: 1 |
| switch plan | PASS | POST /subscription: expected (200,), got 200 |
| missing subscription plan | PASS | POST /subscription: expected (404,), got 404 |
| credit carryover | PASS | GET /active-plan: expected (200,), got 200 |
| credits retained across switch | PASS | creditsUsed=1 |
| deactivate model | PASS | DELETE /admin/api/models/8bc03db6-0b8d-485c-be3b-f3f13e0ab46d: expected (200,), got 200 |
| inactive model cannot predict | PASS | POST /predict: expected (404,), got 404 |
| reactivate model | PASS | PATCH /admin/api/models/8bc03db6-0b8d-485c-be3b-f3f13e0ab46d: expected (200,), got 200 |
| deactivate plan | PASS | DELETE /admin/api/plans/5bc79a15-92f5-4ac8-bd26-7af38460a23c: expected (200,), got 200 |
| inactive plan cannot subscribe | PASS | POST /subscription: expected (404,), got 404 |
| inactive plan fallback | PASS | GET /active-plan: expected (200,), got 200 |
| inactive plan falls back to FREE | PASS | code=FREE |
| reactivate plan | PASS | PATCH /admin/api/plans/5bc79a15-92f5-4ac8-bd26-7af38460a23c: expected (200,), got 200 |
| FREE delete protected | PASS | DELETE /admin/api/plans/06459dab-68ce-4988-aba1-0ad54c1b3686: expected (400,), got 400 |
| FREE deactivate protected | PASS | PATCH /admin/api/plans/06459dab-68ce-4988-aba1-0ad54c1b3686: expected (400,), got 400 |
| promote user | PASS | PATCH /admin/api/users/b92cb575-0d23-4364-aac1-fb679586e703/role: expected (200,), got 200 |
| changed role takes effect | PASS | GET /admin/api/stats: expected (200,), got 200 |
| demote user | PASS | PATCH /admin/api/users/b92cb575-0d23-4364-aac1-fb679586e703/role: expected (200,), got 200 |
| demoted user denied | PASS | GET /admin/api/stats: expected (403,), got 403 |
| invalid role | PASS | PATCH /admin/api/users/b92cb575-0d23-4364-aac1-fb679586e703/role: expected (400,), got 400 |
| missing role target | PASS | PATCH /admin/api/users/missing/role: expected (404,), got 404 |
| change password | PASS | POST /change-password: expected (200,), got 200 |
| old password rejected | PASS | POST /login: expected (401,), got 401 |
| new password accepted | PASS | POST /login: expected (200,), got 200 |
| null profile email rejected | PASS | PATCH /profile: expected (400, 422), got 422 |
| null notifications rejected | PASS | PATCH /settings: expected (400, 422), got 422 |
| blank profile name rejected | PASS | PATCH /profile: expected (400, 422), got 422 |
| oversized profile name rejected | PASS | PATCH /profile: expected (400, 422), got 422 |
| blank profile email rejected | PASS | PATCH /profile: expected (400, 422), got 422 |
| blank account rejected | PASS | POST /register: expected (400, 422), got 422 |
| blank plan create rejected | PASS | POST /admin/api/plans: expected (400, 422), got 422 |
| blank plan update rejected | PASS | PATCH /admin/api/plans/5bc79a15-92f5-4ac8-bd26-7af38460a23c: expected (400, 422), got 422 |
| invalid analyzer Boolean handled | PASS | POST /predict: expected (502,), got 502 |
| offset timestamp prediction | PASS | POST /predict: expected (200,), got 200 |
| PR timestamp keeps its instant | PASS | Analyzer created_at=2026-10-01T12:00:00+06:00; saved history created_at=2026-10-01T06:00:00 |
| admin prediction table matches API | PASS | Admin table uses User, Status, and Created; no removed field references |
