# Canvas Planner

A small personal tool that turns upcoming Canvas coursework into a weekly to-do list. You tap one big **Make Planner** button (it installs as a home-screen app on your phone). That button triggers a Microsoft Power Automate flow, which calls this Flask app to collect the week's tasks and add them to a planner.

## How it works

1. `GET /` serves a single-button page (`templates/index.html`). It's set up as a PWA, so you can add it to your iOS or Android home screen.
2. Pressing the button sends a POST to a Power Automate HTTP trigger (`FLOW_URL`).
3. The flow calls `POST /update_planner` on this app.
4. For each course in `COURSE_SETTINGS`, the app uses the Canvas API to walk the course modules. It collects assignments, pages, discussions, and quizzes that are due between today and 7 days from now, skipping anything you've already submitted.
5. Each item becomes a task with a name, link, due date (in Pacific time), course bucket, and category tags such as `Quiz`, `Reading/Video`, `Short Essay`, and `Discussion`. Per-course `TAG_RULES` assign the tags based on item names and types. `CUSTOM_RULES` can skip items, and anything left unmatched is tagged `Miscellaneous`.
6. The app returns the task list as JSON for the flow to add to the planner.

## Configuration

Courses are set up in `flask_app.py`:

- `COURSE_SETTINGS` maps a display name to `[canvas_client, course_id, tag_rules, search_settings, custom_rules]`.
  - `search_settings` supports `module_limit`, `skip_modules`, `skip_reference`, `first_module_only`, and `enabled`.
  - If `course_id` is `None`, the first value is treated as a path to a JSON file of assignments instead of a Canvas client.
- `TAG_RULES` and `CUSTOM_RULES` match items with `name_contains_any`, `name_contains_all`, `name_not_contains_any`, `type`, and similar conditions, then add `tags`, `clear_tags`, or `set` values, or `skip` the item.
- `DATE_OVERRIDE` sets a fixed cutoff date (`MM/DD/YYYY`) for testing.

### Environment variables

Put these in a `.env` file next to `flask_app.py`:

| Variable | Purpose |
|---|---|
| `DAO_URL`, `DAO_KEY` | Base URL and API access token for the first Canvas instance |
| `NASA_URL`, `NASA_KEY` | Base URL and API access token for a second Canvas instance (optional) |
| `FLOW_URL` | The Power Automate HTTP trigger URL that the button calls |

To create a Canvas access token, open Canvas and go to **Account → Settings → New Access Token**. Treat the token and the Power Automate URL (it includes a signature) like passwords: never commit them.

## Running

```bash
pip install flask canvasapi python-dateutil python-dotenv
python flask_app.py
```

It was originally deployed on PythonAnywhere.
