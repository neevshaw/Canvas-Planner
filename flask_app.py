from canvasapi import Canvas
from canvasapi.page import Page
from canvasapi.discussion_topic import DiscussionTopic
from canvasapi.exceptions import ResourceDoesNotExist
from flask import Flask, jsonify, render_template
from werkzeug.exceptions import HTTPException
from datetime import datetime, timedelta
from copy import copy
from dateutil import tz
from dotenv import load_dotenv
import json
import os
import traceback


from_zone = tz.gettz("UTC")
to_zone = tz.gettz("America/Los_Angeles")

load_dotenv("/home/canvasPlanner/mysite/.env")


# Set to None for normal behavior, or use MM/DD/YYYY (for example, "09/15/2026")
DATE_OVERRIDE = None


def pst(date):
    utc = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
    utc = utc.replace(tzinfo=from_zone)
    return utc.astimezone(to_zone)


def iso(d):
    return d.isoformat()[:19] + "Z"


dao = Canvas(
    os.getenv("DAO_URL"),
    os.getenv("DAO_KEY"),
)

nasa = Canvas(
    os.getenv("NASA_URL"),
    os.getenv("NASA_KEY"),
)


LABELS = [
    "Discussion",
    "Problems",
    "Quiz",
    "Exam",
    "Essay",
    "Project",
    "Self Assessment",
    "Presentation",
    "Notes",
    "Lab",
    "Short Essay",
    "Reading/Video",
    "MyLab & Mastering",
    "Progress Check",
    "Miscellaneous",
]


TAG_RULES = {
    "Real Analysis (DAO)": [
        {
            "match": {
                "name_contains_any": ["Pre-class assignment"],
            },
            "tags": ["Problems", "Notes", "Reading/Video"],
        },
        {
            "match": {
                "name_contains_any": ["HW"],
            },
            "tags": ["Problems"],
        },
        {
            "match": {
                "name_contains_any": ["Exam"],
            },
            "tags": ["Exam"],
        },
    ],
    "American Government (DAO)": [
        {
            "match": {
                "type": ["Discussion"],
                "name_contains_any": ["DQ"]
            },
            "tags": ["Short Essay", "Discussion"],
        },
        {
            "match": {
                "name_contains_any": ["Reading"]
            },
            "tags": ["Reading/Video"],
        },
        {
            "match": {
                "type": ["Assignment"]
            },
            "tags": ["Short Essay"],
        },
    ],
    "American Literature (DAO)": [
        {
            "match": {
                "type": ["Discussion"],
                "name_contains_any": ["DQ"]
            },
            "tags": ["Short Essay", "Discussion"],
        },
        {
            "match": {
                "name_contains_any": ["READ", "WATCH", "LISTEN"]
            },
            "tags": ["Reading/Video"],
        },
        {
            "match": {
                "name_contains_any": ["Self"]
            },
            "tags": ["Self Assessment"],
        },
        {
            "match": {
                "name_contains_any": ["Notes"]
            },
            "tags": ["Reading/Video", "Notes"],
        },
        {
            "match": {
                "name_contains_any": ["HOMEWORK"]
            },
            "tags": ["Short Essay"],
        },
        {
            "match": {
                "name_contains_any": ["PROCESS"]
            },
            "tags": ["Essay"],
        },
        {
            "match": {
                "type": ["Page"]
            },
            "tags": ["Reading/Video"],
        },
    ],
    "Advanced Biology (DAO)": [
        {
            "match": {
                "type": ["Discussion"],
                "name_contains_any": ["DISCUSS"]
            },
            "tags": ["Discussion"],
        },
        {
            "match": {
                "name_contains_any": ["READ", "WATCH", "LISTEN"]
            },
            "tags": ["Reading/Video"],
        },
        {
            "match": {
                "name_contains_any": ["READ & COMPLETE"]
            },
            "tags": ["Notes"],
        },
        {
            "match": {
                "type": ["Quiz"]
            },
            "tags": ["Quiz"],
        },
    ],
    "College Seminar (DAO)": [
        {
            "match": {
                "type": ["Discussion"],
                "name_contains_any": ["DISCUSS"]
            },
            "tags": ["Discussion"],
        },
        {
            "match": {
                "name_contains_any": ["READ", "WATCH", "LISTEN"]
            },
            "tags": ["Reading/Video"],
        },
        {
            "match": {
                "name_contains_any": ["CREATE", "ENGAGE"]
            },
            "tags": ["Short Essay"],
        },
        {
            "match": {
                "name_contains_any": ["REFLECT"]
            },
            "tags": ["Self Assessment"],
        },
    ],
}


CUSTOM_RULES = {
    "Real Analysis (DAO)": [
        {
            "match": {
                "name_contains_any": ["In-Class"],
            },
            "skip": True,
        },
    ],
    "American Literature (DAO)": [],
    "American Government (DAO)": [],
    "Advanced Biology (DAO)": [
        {
            "match": {
                "name_contains_any": ["RESOURCES"],
            },
            "skip": True,
        },
    ],
    "College Seminar (DAO)": [],
}


COURSE_SETTINGS = {
    "Real Analysis (DAO)": [
        dao,
        1497,
        TAG_RULES["Real Analysis (DAO)"],
        {"module_limit": 2},
        CUSTOM_RULES["Real Analysis (DAO)"],
    ],
    "American Literature (DAO)": [
        dao,
        1475,
        TAG_RULES["American Literature (DAO)"],
        {"module_limit": 2},
        CUSTOM_RULES["American Literature (DAO)"],
    ],
    "American Government (DAO)": [
        dao,
        1485,
        TAG_RULES["American Government (DAO)"],
        {"skip_modules": 1, "module_limit": 2},
        CUSTOM_RULES["American Government (DAO)"],
    ],
    "Advanced Biology (DAO)": [
        dao,
        1461,
        TAG_RULES["Advanced Biology (DAO)"],
        {},
        CUSTOM_RULES["Advanced Biology (DAO)"],
    ],
    "College Seminar (DAO)": [
        dao,
        1554,
        TAG_RULES["College Seminar (DAO)"],
        {"module_limit": 1},
        CUSTOM_RULES["College Seminar (DAO)"],
    ]
}

class JSON_Assignment:
    def __init__(self, data):
        for key, value in data.items():
            setattr(self, key, value)

        self.name = data["name"]
        self.due_at = data.get("due_at")
        self.html_url = data.get("html_url")


def is_unsubmitted(assignment):
    submission = getattr(assignment, "submission", None)

    if submission is None:
        return True

    if isinstance(submission, dict):
        return submission.get("submitted_at") is None

    return getattr(submission, "submitted_at", None) is None


def matches(obj, task, match, classified=False):
    if not match:
        return True

    case_sensitive = match.get("case_sensitive", False)

    name = task["name"]
    compare_name = name if case_sensitive else name.lower()

    conditions = []

    if "unclassified" in match:
        conditions.append(
            match["unclassified"] is True and not classified
        )

    allowed_types = match.get("type")

    if allowed_types is not None:
        planner_type = getattr(obj, "_planner_type", None)
        conditions.append(planner_type in allowed_types)

    contains_any = match.get("name_contains_any")

    if contains_any:
        terms = (
            contains_any
            if case_sensitive
            else [x.lower() for x in contains_any]
        )
        conditions.append(
            any(term in compare_name for term in terms)
        )

    contains_all = match.get("name_contains_all")

    if contains_all:
        terms = (
            contains_all
            if case_sensitive
            else [x.lower() for x in contains_all]
        )
        conditions.append(
            all(term in compare_name for term in terms)
        )

    not_contains_any = match.get("name_not_contains_any")

    if not_contains_any:
        terms = (
            not_contains_any
            if case_sensitive
            else [x.lower() for x in not_contains_any]
        )
        conditions.append(
            not any(term in compare_name for term in terms)
        )

    id_startswith = match.get("id_startswith")

    if id_startswith is not None:
        conditions.append(
            str(getattr(obj, "id", "")).startswith(id_startswith)
        )

    attribute_true = match.get("attribute_true")

    if attribute_true is not None:
        conditions.append(
            bool(getattr(obj, attribute_true, False))
        )

    return any(conditions)


def apply_rule(obj, task, rule, classified=False):
    if not matches(
        obj,
        task,
        rule.get("match", {}),
        classified,
    ):
        return False, False

    if rule.get("skip", False):
        return True, True

    changed = False

    for tag in rule.get("tags", []):
        task[tag] = True
        changed = True

    for tag in rule.get("clear_tags", []):
        task[tag] = False
        changed = True

    for key, value in rule.get("set", {}).items():
        task[key] = value
        changed = True

    return changed, False


def apply_rules(obj, task, rules, classified=False):
    changed = False

    for rule in rules:
        rule_changed, skip = apply_rule(
            obj,
            task,
            rule,
            classified or changed,
        )

        if skip:
            return changed, True

        if rule_changed:
            changed = True

    return changed, False


def try_index(getter, key):
    try:
        return {
            key(obj): obj
            for obj in getter()
        }
    except ResourceDoesNotExist:
        return None


def get_canvas_assignments(
    canvas_source,
    course_id,
    start,
    cutoff,
    search_settings,
):
    results = []

    course = canvas_source.get_course(course_id)

    assignments = {
        a.id: a
        for a in course.get_assignments(
            include=["submission"]
        )
    }

    pages = try_index(
        course.get_pages,
        lambda p: p.url,
    )

    quizzes = try_index(
        course.get_quizzes,
        lambda q: q.id,
    )

    discussions = try_index(
        course.get_discussion_topics,
        lambda d: d.id,
    )

    skip_reference = search_settings.get(
        "skip_reference",
        False,
    )

    skip_modules = search_settings.get(
        "skip_modules",
        0,
    )

    first_module_only = search_settings.get(
        "first_module_only",
        False,
    )

    # The original Canvas module iteration is preserved. A limit applies
    # only when explicitly configured (never for Advanced Biology).
    module_limit = search_settings.get("module_limit")

    for module_index, module in enumerate(
        course.get_modules(),
        start=1,
    ):
        if module_limit is not None and module_index > module_limit:
            break

        if (
            skip_reference
            and "Reference" in module.name
        ):
            continue

        if module_index <= skip_modules:
            continue

        for item in module.get_module_items():
            if item.type == "Assignment":
                a = assignments.get(
                    item.content_id
                )

                if (
                    a is not None
                    and a.due_at is not None
                    and start <= a.due_at_date <= cutoff
                    and is_unsubmitted(a)
                ):
                    typed_assignment = copy(a)
                    typed_assignment._planner_type = "Assignment"
                    results.append(typed_assignment)

            elif item.type == "Page":
                if pages is None:
                    try:
                        p = course.get_page(
                            item.page_url
                        )
                    except ResourceDoesNotExist:
                        continue
                else:
                    p = pages.get(
                        item.page_url
                    )

                if (
                    p is not None
                    and p.todo_date is not None
                    and start <= p.todo_date_date <= cutoff
                ):
                    p._planner_type = "Page"
                    results.append(p)

            elif item.type == "Discussion":
                if discussions is None:
                    try:
                        d = course.get_discussion_topic(
                            item.content_id
                        )
                    except ResourceDoesNotExist:
                        continue
                else:
                    d = discussions.get(
                        item.content_id
                    )

                if d is None:
                    continue

                assignment_id = getattr(
                    d,
                    "assignment_id",
                    None,
                )

                if assignment_id:
                    a = assignments.get(
                        assignment_id
                    )

                    if (
                        a is not None
                        and a.due_at is not None
                        and start <= a.due_at_date <= cutoff
                        and is_unsubmitted(a)
                    ):
                        typed_assignment = copy(a)
                        typed_assignment._planner_type = "Discussion"
                        results.append(typed_assignment)

                elif (
                    getattr(d, "todo_date", None) is not None
                    and start <= d.todo_date_date <= cutoff
                ):
                    d._planner_type = "Discussion"
                    results.append(d)

            elif item.type == "Quiz":
                if quizzes is None:
                    try:
                        q = course.get_quiz(
                            item.content_id
                        )
                    except ResourceDoesNotExist:
                        continue
                else:
                    q = quizzes.get(
                        item.content_id
                    )

                if q is None:
                    continue

                assignment_id = getattr(
                    q,
                    "assignment_id",
                    None,
                )

                if assignment_id:
                    a = assignments.get(
                        assignment_id
                    )

                    if (
                        a is not None
                        and a.due_at is not None
                        and start <= a.due_at_date <= cutoff
                        and is_unsubmitted(a)
                    ):
                        typed_assignment = copy(a)
                        typed_assignment._planner_type = "Quiz"
                        results.append(typed_assignment)

                elif (
                    getattr(q, "due_at", None) is not None
                    and start <= q.due_at_date <= cutoff
                ):
                    q._planner_type = "Quiz"
                    results.append(q)

        if first_module_only:
            break

    return results


def get_json_assignments(
    path,
    start,
    cutoff,
):
    with open(path) as f:
        assignments = [
            JSON_Assignment(data)
            for data in json.load(f)
        ]

    results = []

    for assignment in assignments:
        if assignment.due_at is None:
            continue

        due_date = datetime.fromisoformat(
            assignment.due_at.replace(
                "Z",
                "+00:00",
            )
        )

        if start <= due_date <= cutoff:
            results.append(assignment)

    return results


def get_assignments(
    source,
    course_id,
    start,
    cutoff,
    search_settings,
):
    if course_id is None:
        return get_json_assignments(
            source,
            start,
            cutoff,
        )

    return get_canvas_assignments(
        source,
        course_id,
        start,
        cutoff,
        search_settings,
    )


def make_task(
    assignment,
    course_name,
):
    task = {
        "link": assignment.html_url,
        "bucket": course_name,
        **{
            label: False
            for label in LABELS
        },
    }

    if isinstance(assignment, Page):
        task["name"] = assignment.title
        task["due_date"] = iso(
            pst(assignment.todo_date)
        )

    elif isinstance(
        assignment,
        DiscussionTopic,
    ):
        task["name"] = assignment.title
        task["due_date"] = iso(
            pst(assignment.todo_date)
        )
        task["Discussion"] = True

    else:
        task["name"] = assignment.name
        task["due_date"] = iso(
            pst(assignment.due_at)
        )

    return task


app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route(
    "/update_planner",
    methods=["POST"],
)
def update():
    tasks = []

    now = datetime.now(to_zone)
    friday = 1 if now.weekday() == 4 else 0

    start = now + timedelta(
        days=friday
    )

    if DATE_OVERRIDE is None:
        cutoff = (
            now + timedelta(days=7)
        ).replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=999999,
        )
    else:
        override_date = datetime.strptime(
            DATE_OVERRIDE,
            "%m/%d/%Y",
        ).replace(tzinfo=to_zone)

        cutoff = override_date.replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=999999,
        )

    for course_name, settings in COURSE_SETTINGS.items():
        source = settings[0]
        course_id = settings[1]
        tag_rules = settings[2]
        search_settings = settings[3]
        custom_rules = settings[4]

        if not search_settings.get(
            "enabled",
            True,
        ):
            continue

        assignments = get_assignments(
            source,
            course_id,
            start,
            cutoff,
            search_settings,
        )

        for assignment in assignments:
            task = make_task(
                assignment,
                course_name,
            )

            classified, skip = apply_rules(
                assignment,
                task,
                tag_rules,
            )

            if skip:
                continue

            custom_changed, skip = apply_rules(
                assignment,
                task,
                custom_rules,
                classified,
            )

            if skip:
                continue

            classified = (
                classified
                or custom_changed
            )

            if not classified:
                task["Miscellaneous"] = True

            tasks.append(task)

    return jsonify({
        "statusCode": 200,
        "body": json.dumps(tasks),
    })

@app.errorhandler(Exception)
def handle_error(e):
    # Flask uses HTTP exceptions for ordinary 404/405 responses.
    # Preserve their original status codes instead of reporting 500.
    if isinstance(e, HTTPException):
        return e

    app.logger.error(
        "Unhandled exception:\n%s",
        traceback.format_exc()
    )
    return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run()