import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
BRD_PATH = BASE_DIR / "BRD.txt"
OUTPUT_JSON_PATH = BASE_DIR / "epics_and_stories.json"

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_URL = os.getenv(
    "LLM_URL",
    "https://api.apinex.bond/v1/chat/completions"
)
LLM_MODEL = "free/gpt-6-luna"

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "SCRUM")

# Common Jira Cloud Epic Name field ID.
# Verify this field in your own project's create metadata.
EPIC_NAME_FIELD = os.getenv(
    "JIRA_EPIC_NAME_FIELD",
    "customfield_10011"
)

if not LLM_API_KEY:
    raise RuntimeError("Set LLM_API_KEY first.")

if not all([JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN]):
    raise RuntimeError(
        "Set JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_TOKEN."
    )


# ============================================================
# 2. READ THE EXISTING BRD
# ============================================================

def read_brd():
    if not BRD_PATH.exists():
        raise FileNotFoundError(
            f"BRD file not found: {BRD_PATH}"
        )

    brd = BRD_PATH.read_text(encoding="utf-8").strip()

    if not brd:
        raise RuntimeError("BRD.txt is empty.")

    return brd


# ============================================================
# 3. ASK THE LLM TO GENERATE EPICS AND USER STORIES
# ============================================================

def generate_epics_and_stories(brd):
    prompt = """
You are a Senior Business Analyst and Agile Product Owner.

Analyze the supplied Business Requirements Document (BRD).
Break it into a sensible Jira Epic and User Story hierarchy.

BUSINESS ANALYSIS RULES:
1. Create multiple meaningful Epics based on distinct business
   capabilities, not one Epic for the entire project.
2. Place multiple related User Stories under each Epic.
3. Every Story must belong to exactly one Epic.
4. Derive requirements only from the BRD. Do not invent
   unrelated functionality or unsupported business rules.
5. Avoid duplicate, overlapping or excessively granular stories.
6. Write every Story in this format:
   As a [user role], I want [capability], so that [benefit].
7. Give each Story 2 to 5 clear, testable acceptance criteria.
8. Use concise, business-oriented Epic descriptions.
9. Make Epic and Story summaries suitable for Jira.
10. Include enough stories to cover the BRD meaningfully.
    Do not force an arbitrary number of Epics or stories.

Return ONLY valid JSON. Do not use Markdown fences,
comments, explanations or text outside the JSON.

Required JSON structure:
{
  "epics": [
    {
      "summary": "Epic title",
      "description": "Epic business objective and scope",
      "stories": [
        {
          "summary": "User story title",
          "description": "As a ... I want ... so that ...",
          "acceptanceCriteria": [
            "Given ... when ... then ...",
            "Another testable criterion"
          ]
        }
      ]
    }
  ]
}

Every Epic must contain at least one Story.
The top-level property must be named "epics".
"""

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a precise business analyst. "
                    "Return valid JSON only."
                )
            },
            {
                "role": "user",
                "content": (
                        prompt
                        + "\n\nBUSINESS REQUIREMENTS DOCUMENT:\n"
                        + brd
                )
            }
        ],
        "temperature": 0.2
    }

    request = urllib.request.Request(
        url=LLM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}",
            "User-Agent": "BRD-Epic-Story-Generator/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
                request, timeout=180
        ) as response:
            response_text = response.read().decode("utf-8")

    except urllib.error.HTTPError as error:
        details = error.read().decode(
            "utf-8", errors="replace"
        )
        raise RuntimeError(
            f"LLM API error {error.code}: {details}"
        ) from error

    root = json.loads(response_text)

    content = (
        root.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM returned empty JSON content.")

    # Tolerate a response surrounded by Markdown JSON fences.
    content = content.strip()
    content = re.sub(
        r"^```(?:json)?\s*",
        "",
        content,
        flags=re.IGNORECASE
    )
    content = re.sub(r"\s*```$", "", content)

    try:
        result = json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "LLM did not return valid JSON. "
            f"Response begins: {content[:1000]}"
        ) from error

    validate_generated_data(result)
    return result


# ============================================================
# 4. VALIDATE THE LLM OUTPUT BEFORE CREATING JIRA ISSUES
# ============================================================

def validate_generated_data(data):
    if not isinstance(data, dict):
        raise ValueError("The generated result must be a JSON object.")

    epics = data.get("epics")

    if not isinstance(epics, list) or not epics:
        raise ValueError("No Epics were generated.")

    for epic_index, epic in enumerate(epics, start=1):

        if not isinstance(epic, dict):
            raise ValueError(f"Epic {epic_index} is invalid.")

        if not isinstance(epic.get("summary"), str):
            raise ValueError(
                f"Epic {epic_index} has no valid summary."
            )

        epic["summary"] = epic["summary"].strip()

        if not epic["summary"]:
            raise ValueError(f"Epic {epic_index} has an empty summary.")

        if not isinstance(epic.get("description"), str):
            raise ValueError(
                f"Epic {epic_index} has no valid description."
            )

        stories = epic.get("stories")

        if not isinstance(stories, list) or not stories:
            raise ValueError(
                f"Epic {epic_index} must contain at least one Story."
            )

        for story_index, story in enumerate(stories, start=1):

            if not isinstance(story, dict):
                raise ValueError(
                    f"Story {story_index} in Epic {epic_index} is invalid."
                )

            for field in ("summary", "description"):
                if not isinstance(story.get(field), str):
                    raise ValueError(
                        f"Story {story_index} in Epic {epic_index} "
                        f"has no valid {field}."
                    )

                story[field] = story[field].strip()

                if not story[field]:
                    raise ValueError(
                        f"Story {story_index} has an empty {field}."
                    )

            criteria = story.get("acceptanceCriteria")

            if (
                    not isinstance(criteria, list)
                    or not 2 <= len(criteria) <= 5
                    or any(
                not isinstance(item, str) or not item.strip()
                for item in criteria
            )
            ):
                raise ValueError(
                    f"Story {story_index} in Epic {epic_index} "
                    "must have 2-5 non-empty acceptance criteria."
                )

    print(
        f"Validated {len(epics)} Epics and "
        f"{sum(len(e['stories']) for e in epics)} User Stories."
    )


# ============================================================
# 5. JIRA CLOUD REST API HELPER
# ============================================================

def jira_request(method, endpoint, payload=None):
    credentials = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode("utf-8")
    encoded_credentials = base64.b64encode(
        credentials
    ).decode("ascii")

    body = None

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=f"{JIRA_BASE_URL}{endpoint}",
        data=body,
        headers={
            "Authorization": f"Basic {encoded_credentials}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        },
        method=method
    )

    try:
        with urllib.request.urlopen(
                request, timeout=60
        ) as response:
            response_body = response.read().decode("utf-8")
            return (
                json.loads(response_body)
                if response_body.strip()
                else {}
            )

    except urllib.error.HTTPError as error:
        details = error.read().decode(
            "utf-8", errors="replace"
        )

        raise RuntimeError(
            f"Jira API failed: {method} {endpoint}; "
            f"HTTP {error.code}; response: {details}"
        ) from error


# ============================================================
# 6. CONVERT TEXT TO JIRA CLOUD DESCRIPTION FORMAT (ADF)
# ============================================================

def to_adf(text):
    paragraphs = []

    for line in text.splitlines():
        paragraphs.append({
            "type": "paragraph",
            "content": (
                [{"type": "text", "text": line}]
                if line else []
            )
        })

    if not paragraphs:
        paragraphs = [{
            "type": "paragraph",
            "content": []
        }]

    return {
        "type": "doc",
        "version": 1,
        "content": paragraphs
    }


def build_story_description(story):
    criteria = story["acceptanceCriteria"]

    criteria_text = "\n".join(
        f"{index}. {criterion}"
        for index, criterion in enumerate(criteria, start=1)
    )

    return (
            story["description"]
            + "\n\nAcceptance Criteria:\n"
            + criteria_text
    )


# ============================================================
# 7. CREATE AN EPIC IN JIRA
# ============================================================


def create_epic(epic):
    fields = {
        "project": {
            "key": JIRA_PROJECT_KEY
        },
        "issuetype": {
            "id": "10001"
        },
        "summary": epic["summary"],
        "description": to_adf(epic["description"])
    }

    response = jira_request(
        "POST",
        "/rest/api/3/issue",
        {"fields": fields}
    )

    return response["key"]


# ============================================================
# 8. CREATE A STORY UNDER ITS EPIC
# ============================================================

def create_story(story, epic_key):
    description = build_story_description(story)

    fields = {
        "project": {"key": JIRA_PROJECT_KEY},
        "issuetype": {"name": "Story"},
        "summary": story["summary"],
        "description": to_adf(description),

        # This establishes the Story's parent Epic in Jira Cloud.
        "parent": {"key": epic_key}
    }

    response = jira_request(
        "POST",
        "/rest/api/3/issue",
        {"fields": fields}
    )

    story_key = response.get("key")

    if not story_key:
        raise RuntimeError(
            f"Jira did not return a Story key: {response}"
        )

    print(
        f"  Created Story: {story_key} - {story['summary']} "
        f"(parent Epic: {epic_key})"
    )

    return story_key


# ============================================================
# 9. CREATE ALL EPICS FIRST, THEN THEIR STORIES
# ============================================================

def upload_to_jira(data):
    created_items = []

    for epic_number, epic in enumerate(
            data["epics"], start=1
    ):

        print(
            f"\nCreating Epic {epic_number}: {epic['summary']}"
        )

        # Step A: Create the Epic first.
        epic_key = create_epic(epic)

        created_items.append({
            "type": "Epic",
            "key": epic_key,
            "summary": epic["summary"],
            "url": f"{JIRA_BASE_URL}/browse/{epic_key}"
        })

        # Step B: Create all its stories under that Epic.
        for story in epic["stories"]:
            story_key = create_story(story, epic_key)

            created_items.append({
                "type": "Story",
                "key": story_key,
                "summary": story["summary"],
                "parentEpic": epic_key,
                "url": f"{JIRA_BASE_URL}/browse/{story_key}"
            })

    return created_items


# ============================================================
# 10. MAIN WORKFLOW
# ============================================================


def find_epic_name_field():
    print("Checking Epic creation metadata...")

    # Get issue types available in the SCRUM project.
    metadata = jira_request(
        "GET",
        "/rest/api/3/issue/createmeta/SCRUM/issuetypes"
    )

    issue_types = metadata.get("issueTypes", [])

    print("\nAvailable issue types:")

    for issue_type in issue_types:
        print(
            f"Name: {issue_type.get('name')} | "
            f"ID: {issue_type.get('id')} | "
            f"Subtask: {issue_type.get('subtask')}"
        )

        if issue_type.get("name", "").lower() == "epic":
            epic_id = issue_type["id"]

            print("\nFetching fields available for Epic...")

            details = jira_request(
                "GET",
                f"/rest/api/3/issue/createmeta/SCRUM/"
                f"issuetypes/{epic_id}"
            )

            for field in details.get("fields", []):
                print(
                    f"Name: {field.get('name')} | "
                    f"ID: {field.get('fieldId')} | "
                    f"Required: {field.get('required')} | "
                    f"Operations: {field.get('operations')}"
                )


def main():
    brd = read_brd()

    if OUTPUT_JSON_PATH.exists():
        print("Using existing generated hierarchy...")
        with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as file:
            generated_data = json.load(file)
    else:
        print("Generating Epics and User Stories using the LLM...")
        generated_data = generate_epics_and_stories(brd)

        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as file:
            json.dump(generated_data, file, indent=2, ensure_ascii=False)

    # created_items = upload_to_jira(generated_data)

    # Save the proposed hierarchy before uploading it.
    OUTPUT_JSON_PATH.write_text(
        json.dumps(
            generated_data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(f"Generated hierarchy saved to: {OUTPUT_JSON_PATH}")

    print("\nUploading Epics and Stories to Jira...")
    created_items = upload_to_jira(generated_data)

    print("\n" + "=" * 60)
    print("JIRA UPLOAD SUMMARY")
    print("=" * 60)

    for item in created_items:
        print(
            f"{item['type']}: {item['key']} | "
            f"{item['summary']}\n"
            f"URL: {item['url']}"
        )

    print(f"\nTotal issues created: {len(created_items)}")
    print("Upload process completed.")

if __name__ == "__main__":
    main()
