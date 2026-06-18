# Skylight (family calendar) — Private API Reference

> **Unofficial.** This documents the private REST API used by the Skylight
> family-calendar apps at `ourskylight.com` / `app.ourskylight.com`. It is
> reverse-engineered from the web client and is **not** supported by Skylight.
> It can change or break without notice. Use only with an account you own.
>
> ⚠️ This is **not** the same product as `api.skylight.earth` (a maritime
> domain-awareness GraphQL API by an unrelated organization that happens to
> share the name).

## Base URL

```
https://app.ourskylight.com/api
```

## Required headers

Every request must advertise a recent client version or the API responds with
`401 {"errors":["This version of Skylight is no longer supported..."]}`.

| Header | Value |
| --- | --- |
| `Accept` | `application/json` |
| `Content-Type` | `application/json` (for POST/PATCH) |
| `Skylight-Api-Version` | `2026-05-01` |
| `User-Agent` | `SkylightMobile (web)` |
| `Authorization` | `Bearer <access_token>` |

## Authentication

Skylight uses **OAuth2** (Doorkeeper) with opaque, **rotating** tokens.

> ⚠️ **The old email/password `POST /api/sessions` flow is sunset.** As of
> June 2026 every `Skylight-Api-Version` value is rejected there with
> `401 {"errors":["This version of Skylight is no longer supported..."]}`
> (recognised versions like `2026-06-01` are "deprecated"; everything else is
> "Invalid API version"). The apps now authenticate via OAuth. Don't build on
> `/api/sessions`.

### Token endpoint (refresh-token grant)

```
POST https://app.ourskylight.com/oauth/token        ← note: NOT under /api
Content-Type: application/json

{ "grant_type": "refresh_token",
  "refresh_token": "<refresh_token>",
  "client_id": "skylight-mobile" }
```

Response (`200`):

```json
{ "access_token": "…", "token_type": "Bearer", "expires_in": 7200,
  "refresh_token": "…(ROTATED)…", "scope": "everything", "created_at": 1781… }
```

* **Public client** — `client_id: "skylight-mobile"`, **no client secret**.
* `access_token` is a Bearer token, **valid 2 hours**.
* The `refresh_token` **rotates on every call** — the old one is revoked, so you
  must persist the new one for next time. (Two clients cannot share one refresh
  chain.)
* `scope: "everything"` → full account read + write.
* Also present: `/oauth/authorize` (authorization-code flow, used by the apps'
  interactive login) and `/oauth/revoke`.

### Bootstrapping a refresh token

There's no headless password login anymore, so capture a refresh token once:
sign in at `ourskylight.com`, then in DevTools → Application → Local Storage →
`mmkv.default\auth-storage` → copy `state.refreshToken`. Feed it to the client;
it self-renews from there.

### Security note

A refresh token → a full-access (`everything`) token with no finer scoping.
Treat it like a password. Access tokens are short-lived (2h) and the refresh
chain is server-side revocable (and rotates), which limits exposure.

## Data shape

Responses are **JSON:API**:

```json
{ "data": [ { "type": "category", "id": "123",
              "attributes": { … },
              "relationships": { "category": { "data": { "type": "category", "id": "9" } } } } ],
  "included": [ … ] }
```

---

## Endpoints

`{f}` = frame id. Discover yours via `GET /api/frames`.

### Frames / account

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/frames` | List frames (calendars) for the login |
| GET | `/frames/{f}` | Frame detail (name, timezone, apps…) |
| GET | `/frames/{f}/devices` | Physical Skylight devices |
| GET | `/frames/{f}/household_config` | Household settings |
| GET | `/frames/{f}/users` | Users with access |
| PATCH | `/frames/{f}/rename` | Rename frame |

### Categories (profiles **and** labels)

A "category" with `linked_to_profile: true` is a **person/profile**; otherwise
it is a **label**.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/frames/{f}/categories` | All profiles + labels |
| POST | `/frames/{f}/categories` | Create. Body: `{label, color, linked_to_profile}` |
| PATCH | `/frames/{f}/categories/{id}` | Update. Body: `{label, color, …}` |
| DELETE | `/frames/{f}/categories/{id}` | Delete |
| DELETE | `/frames/{f}/categories/{id}?reassign_to_category_id={tgt}` | **Merge**: move events/tasks/rewards to `{tgt}`, delete source |

`attributes`: `label`, `color` (`#RRGGBB`), `linked_to_profile`,
`selected_for_chore_chart`, `profile_picture_urls`.

### Calendar events

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/frames/{f}/calendar_events?date_min=YYYY-MM-DD&date_max=YYYY-MM-DD&timezone=America/Phoenix` | Events in range |
| GET | `/frames/{f}/calendar_events/{id}` | Event detail |
| GET | `/frames/{f}/calendar_events/search?q=…` | Search |
| GET | `/frames/{f}/calendar_events/countdowns` | Countdown events |
| POST | `/frames/{f}/calendar_events` | Create |
| PATCH | `/frames/{f}/calendar_events/{id}` | Update |
| DELETE | `/frames/{f}/calendar_events/{id}` | Delete |

`attributes` (observed): `uid`, `summary`, `description`, `location`,
`all_day`, `starts_at`, `ends_at`, `timezone`, `recurring`, `rrule`,
`master_event_id`, `status`, `source`, `kind`, `owner_email`, `calendar_id`,
`countdown_enabled`. `relationships.category` → owning profile/label.

### Chores

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/frames/{f}/chores?after=YYYY-MM-DD&before=YYYY-MM-DD&include_late=true` | Chores in range |
| GET | `/frames/{f}/chores/all` | All chores |
| POST | `/frames/{f}/chores` | Create |
| POST | `/frames/{f}/chores/create_multiple` | Bulk create |
| POST | `/frames/{f}/chores/{id}/completions` | Mark complete |
| GET | `/frames/{f}/chores/{id}/completions` | Completion history |

`attributes`: `summary`, `status` (`pending`…), `start`, `start_time`,
`completed_on`, `is_future`, `recurring`, `recurrence_set` (RRULE),
`reward_points`, `emoji_icon`, `routine`, `position`. `relationships.category`.

### Task box

| Method | Path |
| --- | --- |
| GET / POST | `/frames/{f}/task_box/items` |
| PATCH / DELETE | `/frames/{f}/task_box/items/{id}` |

`attributes`: `summary`, `emoji_icon`, `routine`, `reward_points`.

### Lists

| Method | Path | Notes |
| --- | --- | --- |
| GET / POST | `/frames/{f}/lists` | Lists |
| GET / PATCH / DELETE | `/frames/{f}/lists/{id}` | A list (items in `included`) |
| GET / POST | `/frames/{f}/lists/{id}/list_items` | Items |
| PATCH / DELETE | `/frames/{f}/lists/{id}/list_items/{id}` | An item |
| POST | `/frames/{f}/lists/{id}/list_items/{id}/move` | Reorder |
| POST | `/frames/{f}/lists/{id}/list_items/bulk_destroy` | Bulk delete |

List `attributes`: `label`, `color`, `kind` (`shopping` \| `to_do`),
`default_grocery_list`. Item `attributes`: `label`,
`status` (`pending` \| `completed`), `section`, `position`, `created_at`.

### Meals

| Method | Path |
| --- | --- |
| GET | `/frames/{f}/meals/recipes` |
| GET | `/frames/{f}/meals/recipes/{id}` |
| POST | `/frames/{f}/meals/recipes/{id}/add_to_grocery_list` |
| GET | `/frames/{f}/meals/sittings` |
| GET | `/frames/{f}/meals/categories` |

### Rewards

| Method | Path | Notes |
| --- | --- | --- |
| GET / POST | `/frames/{f}/rewards` | Rewards catalog |
| POST | `/frames/{f}/rewards/{id}/redeem` | Redeem |
| POST | `/frames/{f}/rewards/{id}/unredeem` | Undo redeem |
| GET | `/frames/{f}/reward_points` | Per-profile point balances |

### Calendars (sources)

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/frames/{f}/source_calendars` | Linked Google/Apple calendars |
| GET | `/frames/{f}/calendars` | Calendars |
| POST | `/frames/{f}/source_calendars/set_default_for_new_events` | Default |

### Photos / messages

| Method | Path |
| --- | --- |
| GET | `/frames/{f}/albums`, `/frames/{f}/albums/{id}/messages` |
| GET / POST | `/frames/{f}/messages` |

---

## Quick test (cURL)

```bash
TOKEN=...   # captured Bearer token
FRAME=...   # your frame id

curl "https://app.ourskylight.com/api/frames/$FRAME/categories" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Skylight-Api-Version: 2026-05-01" \
  -H "User-Agent: SkylightMobile (web)" \
  -H "Accept: application/json"
```

Endpoint inventory cross-checked against two community references —
[`mightybandito/Skylight`](https://github.com/mightybandito/Skylight)
(JSON:API schemas, GET/POST/PATCH/PUT/DELETE coverage) and
[`TheEagleByte/skylight-api`](https://github.com/TheEagleByte/skylight-api)
(a HAR→OpenAPI generator whose spec confirmed the `/api/sessions` login body
`{email, password}` and the `/api/users`, `/api/avatars`, `/api/colors`
endpoints) — plus first-hand capture of the web client (auth flow, version
header `2026-05-01`, 2h token lifetime, and the full 103-path list).
