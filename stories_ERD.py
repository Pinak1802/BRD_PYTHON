import os
import json
import re
import time
import requests

from pathlib import Path
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

# ============================================================
# 1. CONFIGURATION
# ============================================================

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "SCRUM")

LLM_URL = os.getenv(
    "LLM_URL",
    "https://api.apinex.bond/v1/chat/completions"
)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "free/gpt-6-luna")

# Cloud rendering endpoint; not Mermaid Ink.
KROKI_URL = os.getenv(
    "KROKI_URL",
    "https://kroki.io/mermaid/png"
)

# Set these to your Jira instance's actual field IDs.
EPIC_LINK_FIELD = os.getenv(
    "JIRA_EPIC_LINK_FIELD",
    "customfield_10014"
)
ACCEPTANCE_CRITERIA_FIELD = os.getenv(
    "JIRA_ACCEPTANCE_CRITERIA_FIELD",
    "customfield_10016"
)

OUTPUT_DIR = Path("jira_erd_output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HIERARCHY_FILE = OUTPUT_DIR / "jira_epics_and_stories.json"
ERD_FILE = OUTPUT_DIR / "erd.json"
MERMAID_FILE = OUTPUT_DIR / "erd_diagram.mmd"
PNG_FILE = OUTPUT_DIR / "erd_diagram.png"

if not all([JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN]):
    raise ValueError(
        "Configure JIRA_BASE_URL, JIRA_EMAIL and "
        "JIRA_API_TOKEN in your .env file."
    )

jira_auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)

jira_headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}


# ============================================================
# 2. JIRA API HELPERS
# ============================================================

def jira_search_all(jql, fields):
    """Fetch every issue matching JQL using pagination."""

    issues = []
    next_page_token = None

    while True:
        payload = {
            "jql": jql,
            "fields": fields,
            "maxResults": 100
        }

        if next_page_token:
            payload["nextPageToken"] = next_page_token

        response = requests.post(
            f"{JIRA_BASE_URL}/rest/api/3/search/jql",
            auth=jira_auth,
            headers=jira_headers,
            json=payload,
            timeout=(15, 90)
        )
        response.raise_for_status()

        data = response.json()
        page = data.get("issues", [])
        issues.extend(page)

        print(
            f"Fetched {len(page)} issues; "
            f"total = {len(issues)}"
        )

        next_page_token = data.get("nextPageToken")

        if not next_page_token or not page:
            break

    return issues


def jira_field_value(issue, field_name):
    return (issue.get("fields") or {}).get(field_name)


def clean_text(value):
    """Convert Jira text and Atlassian Document Format to text."""

    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return "\n".join(clean_text(item) for item in value)

    if isinstance(value, dict):
        parts = []

        if value.get("text"):
            parts.append(value["text"])

        for item in value.get("content", []):
            parts.append(clean_text(item))

        if parts:
            return "\n".join(part for part in parts if part)

        return ""

    return str(value)


def normalize_issue(issue):
    fields = issue.get("fields", {})
    issue_type = fields.get("issuetype") or {}
    parent = fields.get("parent") or {}
    status = fields.get("status") or {}

    epic_link = jira_field_value(issue, EPIC_LINK_FIELD)

    # Older Jira configurations may return an Epic Link key.
    if isinstance(epic_link, dict):
        epic_link = epic_link.get("key")

    return {
        "key": issue.get("key", ""),
        "issue_type": issue_type.get("name", ""),
        "summary": fields.get("summary") or "",
        "description": clean_text(fields.get("description")),
        "acceptance_criteria": clean_text(
            jira_field_value(issue, ACCEPTANCE_CRITERIA_FIELD)
        ),
        "parent_key": parent.get("key"),
        "epic_link": epic_link,
        "status": status.get("name", "")
    }


# ============================================================
# 3. DOWNLOAD EPICS AND THEIR CHILD ISSUES
# ============================================================

def download_epics_and_stories():
    print("\nDownloading Epics...")

    epic_fields = [
        "summary",
        "description",
        "issuetype",
        "status",
        "parent"
    ]

    raw_epics = jira_search_all(
        f'project = "{PROJECT_KEY}" '
        f'AND issuetype = Epic ORDER BY key ASC',
        epic_fields
    )

    epics = [normalize_issue(issue) for issue in raw_epics]

    print(f"\nFound {len(epics)} Epics.")

    print("\nDownloading project issues...")

    issue_fields = [
        "summary",
        "description",
        "issuetype",
        "status",
        "parent",
        EPIC_LINK_FIELD,
        ACCEPTANCE_CRITERIA_FIELD
    ]

    raw_issues = jira_search_all(
        f'project = "{PROJECT_KEY}" ORDER BY key ASC',
        issue_fields
    )

    issues = [normalize_issue(issue) for issue in raw_issues]

    hierarchy = []

    for epic in epics:
        children = []

        for issue in issues:
            if issue["key"] == epic["key"]:
                continue

            if (
                issue["parent_key"] == epic["key"]
                or issue["epic_link"] == epic["key"]
            ):
                children.append(issue)

        hierarchy.append({
            "epic_key": epic["key"],
            "epic_summary": epic["summary"],
            "epic_description": epic["description"],
            "stories": children
        })

    result = {
        "project_key": PROJECT_KEY,
        "epic_count": len(epics),
        "story_count": sum(
            len(epic["stories"]) for epic in hierarchy
        ),
        "epics": hierarchy
    }

    HIERARCHY_FILE.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"\nSaved hierarchy: {HIERARCHY_FILE}")
    print(f"Epics: {result['epic_count']}")
    print(f"Associated issues: {result['story_count']}")

    return result


# ============================================================
# 4. LOAD SAVED JIRA DATA
# ============================================================

def load_hierarchy():
    if not HIERARCHY_FILE.exists():
        return download_epics_and_stories()

    print(f"\nLoading saved Jira hierarchy: {HIERARCHY_FILE}")

    return json.loads(
        HIERARCHY_FILE.read_text(encoding="utf-8")
    )


# ============================================================
# 5. LLM CALL: GENERATE ERD JSON AND MERMAID SOURCE
# ============================================================

def strip_json_fences(content):
    content = content.strip()

    if content.startswith("```"):
        lines = content.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        content = "\n".join(lines).strip()

    return content


def _safe_identifier(value, fallback="Entity"):
    """Convert a name to a Mermaid-safe identifier."""
    text = re.sub(r"[^A-Za-z0-9_]", "_", str(value or "").strip())
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = fallback
    if text[0].isdigit():
        text = "T_" + text
    return text


def _mermaid_type(value):
    """Convert SQL-like types to simple Mermaid attribute types."""
    value = str(value or "string").strip().upper()
    if value in {"INT", "INTEGER", "SMALLINT", "BIGINT", "SERIAL", "BIGSERIAL"}:
        return "int"
    if value in {"BOOL", "BOOLEAN"}:
        return "boolean"
    if value in {"DATE"}:
        return "date"
    if "TIME" in value:
        return "datetime"
    if "DECIMAL" in value or "NUMERIC" in value or "NUMBER" in value or "FLOAT" in value:
        return "decimal"
    if value in {"TEXT", "VARCHAR", "CHAR", "STRING"} or value.startswith(("VARCHAR", "CHAR")):
        return "string"
    return _safe_identifier(value, "string").lower()


def build_database_mermaid(erd):
    """
    Build Mermaid ER source from the structured schema.
    Unlike the previous implementation, every entity includes its columns,
    and relationships are generated from the same schema object.
    """
    entities = erd.get("entities", [])
    relationships = erd.get("relationships", [])

    if not entities:
        raise ValueError("The ERD has no entities to render.")

    # Map model names to stable Mermaid-safe identifiers.
    name_to_id = {}
    used_ids = set()
    for entity in entities:
        original = str(entity.get("name", "")).strip()
        if not original:
            raise ValueError("An ERD entity is missing its name.")
        base = _safe_identifier(original)
        identifier = base
        suffix = 2
        while identifier.lower() in used_ids:
            identifier = f"{base}_{suffix}"
            suffix += 1
        used_ids.add(identifier.lower())
        name_to_id[original.casefold()] = identifier

    lines = [
        "%%{init: {",
        '  "theme": "default",',
        '  "themeVariables": {',
        '    "background": "#ffffff",',
        '    "primaryColor": "#f4f7fb",',
        '    "primaryBorderColor": "#526d82",',
        '    "primaryTextColor": "#172b4d",',
        '    "lineColor": "#526d82",',
        '    "tertiaryColor": "#ffffff"',
        "  }",
        "}}%%",
        "erDiagram",
        "    direction TB",
    ]

    # Relationships first, followed by full table definitions.
    cardinality_map = {
        "one-to-one": "||--||",
        "one-to-many": "||--o{",
        "many-to-one": "}o--||",
        "many-to-many": "}o--o{",
    }

    for rel in relationships:
        from_name = str(rel.get("from", "")).strip()
        to_name = str(rel.get("to", "")).strip()
        from_id = name_to_id.get(from_name.casefold())
        to_id = name_to_id.get(to_name.casefold())
        if not from_id or not to_id:
            # Skip relationships that point to undeclared entities rather than
            # outputting invalid Mermaid syntax.
            continue
        cardinality = str(rel.get("cardinality", "one-to-many")).lower()
        connector = cardinality_map.get(cardinality, "||--o{")
        label = re.sub(r"[^A-Za-z0-9_ ]", "", str(rel.get("label", "relates to")))
        label = " ".join(label.split())[:40] or "relates to"
        lines.append(f'    {from_id} {connector} {to_id} : "{label}"')

    for entity in entities:
        entity_name = str(entity.get("name", "")).strip()
        entity_id = name_to_id[entity_name.casefold()]
        lines.append("")
        lines.append(f"    {entity_id} {{")

        attributes = entity.get("attributes", [])
        if not isinstance(attributes, list) or not attributes:
            # A table without columns is not useful as a database-style ERD.
            lines.append("        string schema_details")
        else:
            seen_attributes = set()
            for attribute in attributes:
                if not isinstance(attribute, dict):
                    continue
                column_name = _safe_identifier(attribute.get("name", "column"), "column").lower()
                if column_name in seen_attributes:
                    continue
                seen_attributes.add(column_name)

                data_type = _mermaid_type(attribute.get("type", "string"))
                keys = []
                if attribute.get("primary_key") is True:
                    keys.append("PK")
                if attribute.get("foreign_key") is True:
                    keys.append("FK")
                key_text = " " + " ".join(keys) if keys else ""
                lines.append(f"        {data_type} {column_name}{key_text}")

        lines.append("    }")

    return "\n".join(lines) + "\n"


#todo added
def compact_hierarchy(hierarchy):
    compact_epics = []

    for epic in hierarchy.get("epics", []):
        compact_epics.append({
            "epic_summary": epic.get("epic_summary", ""),
            # Keep only concise requirement text so the model has room to
            # return a complete, valid schema instead of truncating its output.
            "epic_description": str(epic.get("epic_description", ""))[:500],
            "stories": [
                {
                    "summary": str(story.get("summary", ""))[:180],
                    "description": str(story.get("description", ""))[:450],
                    "acceptance_criteria": str(
                        story.get("acceptance_criteria", "")
                    )[:300]
                }
                for story in epic.get("stories", [])
            ]
        })

    return {
        "project_key": hierarchy.get("project_key"),
        "epics": compact_epics
    }


def generate_erd_and_mermaid(hierarchy):
    if not LLM_API_KEY:
        raise ValueError("Set LLM_API_KEY in your .env file.")

    requirements = json.dumps(
        compact_hierarchy(hierarchy),
        ensure_ascii=False
    )

    system_prompt = r"""
You are a senior business analyst and relational database architect.

Analyze the complete Jira Epic and Story requirements and design a logical relational
database ERD for the BUSINESS DOMAIN, not a diagram of Jira itself.

IMPORTANT: this must be a DATABASE TABLE ERD, not a network of entity names.
Every entity must have a useful list of columns. Include primary keys, foreign keys,
appropriate data types, and relationships with accurate cardinality.

Rules:
1. Infer only entities and columns supported by the supplied requirements.
2. Every entity must contain an "attributes" array with columns.
3. Each attribute must contain: name, type, primary_key (boolean), foreign_key (boolean).
4. Every entity should normally have one primary key. Use a natural key only when supported;
   otherwise use a sensible generated identifier such as member_id.
5. Include foreign-key columns for relationships where justified by the requirements.
6. Do not create a foreign key just because two concepts are mentioned together.
7. Avoid duplicate entities, redundant attributes, and unsupported assumptions.
8. Use simple SQL-like data types: INTEGER, BIGINT, VARCHAR(255), TEXT, DATE,
   TIMESTAMP, BOOLEAN, DECIMAL(12,2).
9. Relationship cardinality must be one-to-one, one-to-many, many-to-one, or many-to-many.
10. Use entity names that can be converted to uppercase snake-case table names.
11. If details are unclear, record a concise assumption instead of inventing business rules.
12. Keep the output compact: normally 6-12 entities, maximum 15 entities, and maximum
    8 attributes per entity. Prioritize the core business data model.
13. Keep descriptions and labels short (under 10 words).
14. Return one valid JSON object only. Do not use Markdown fences or text outside JSON.
15. Do NOT return Mermaid. The Python program will generate Mermaid from your schema
    to guarantee that all tables display their columns.

Required response structure:
{
  "erd": {
    "entities": [
      {
        "name": "Member",
        "description": "A person enrolled in the scheme",
        "attributes": [
          {
            "name": "member_id",
            "type": "INTEGER",
            "primary_key": true,
            "foreign_key": false
          },
          {
            "name": "scheme_id",
            "type": "INTEGER",
            "primary_key": false,
            "foreign_key": true
          }
        ]
      }
    ],
    "relationships": [
      {
        "from": "Scheme",
        "to": "Member",
        "label": "has",
        "cardinality": "one-to-many"
      }
    ],
    "assumptions": []
  }
}
"""

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": (
                    "Generate the database ERD JSON schema only for these combined Jira "
                    "requirements. Include table columns, SQL-like data types, "
                    "PK/FK flags, relationships and cardinalities:\n\n" + requirements
                )
            }
        ],
        "temperature": 0,
        "max_tokens": 12000,
        # Supported by many OpenAI-compatible APIs; encourages valid JSON.
        "response_format": {"type": "json_object"}
    }

    if not LLM_API_KEY:
        raise ValueError("LLM_API_KEY is missing.")

    generated = None
    last_error = None
    raw_path = OUTPUT_DIR / "llm_raw_response.txt"

    for attempt in range(1, 4):
        try:
            print(f"\nCalling LLM, attempt {attempt}/3...")

            response = requests.post(
                LLM_URL,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload,
                # Longer read timeout helps with large Jira requirements.
                timeout=(20, 240)
            )

            if response.status_code in (429, 500, 502, 503, 504, 524):
                last_error = (
                    f"Temporary LLM HTTP error {response.status_code}: "
                    f"{response.text[:1500]}"
                )
                if attempt < 3:
                    print(last_error)
                    time.sleep(attempt * 5)
                    continue
                response.raise_for_status()

            response.raise_for_status()

            try:
                result = response.json()
            except ValueError as exc:
                raw_path.write_text(response.text, encoding="utf-8")
                last_error = (
                    f"LLM returned a non-JSON HTTP response. "
                    f"Raw response saved to {raw_path}. Details: {exc}"
                )
                if attempt < 3:
                    print(last_error)
                    time.sleep(attempt * 5)
                    continue
                raise RuntimeError(last_error) from exc

            choices = result.get("choices") or []
            message = choices[0].get("message") if choices else None
            content = message.get("content") if isinstance(message, dict) else None

            # Some OpenAI-compatible providers return null content with a
            # refusal, tool call, or provider-side error. Preserve the body.
            if not isinstance(content, str) or not content.strip():
                raw_path.write_text(
                    json.dumps(result, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
                finish_reason = choices[0].get("finish_reason") if choices else None
                message_keys = list(message.keys()) if isinstance(message, dict) else []
                last_error = (
                    "LLM response did not contain text in "
                    "choices[0].message.content. "
                    f"finish_reason={finish_reason!r}; "
                    f"message_keys={message_keys}; "
                    f"full response saved to {raw_path}."
                )
                if attempt < 3:
                    print(last_error)
                    time.sleep(attempt * 5)
                    continue
                raise RuntimeError(last_error)

            content = strip_json_fences(content)

            try:
                generated = json.loads(content)
            except json.JSONDecodeError as exc:
                raw_path.write_text(content, encoding="utf-8")
                finish_reason = choices[0].get("finish_reason") if choices else None
                last_error = (
                    f"LLM returned invalid JSON. finish_reason={finish_reason!r}. "
                    f"Raw response saved to {raw_path}. Error: {exc}"
                )
                if attempt < 3:
                    print(last_error)
                    time.sleep(attempt * 5)
                    continue
                raise ValueError(last_error) from exc

            # Valid response; stop retrying.
            break

        except requests.exceptions.Timeout as exc:
            last_error = f"LLM request timed out: {exc}"
            if attempt == 3:
                raise RuntimeError(
                    f"{last_error}. Try again later or reduce the amount "
                    "of Jira data sent to the LLM."
                ) from exc
            print(last_error + "; retrying...")
            time.sleep(attempt * 5)

        except requests.exceptions.RequestException as exc:
            last_error = f"LLM HTTP request failed: {exc}"
            if attempt == 3:
                raise RuntimeError(last_error) from exc
            print(last_error + "; retrying...")
            time.sleep(attempt * 5)

    if not isinstance(generated, dict):
        raise RuntimeError(
            "Could not obtain a valid JSON ERD from the LLM. "
            f"Last error: {last_error or 'unknown error'}"
        )

    # Accept either {"erd": {...}} or a direct ERD object for resilience.
    erd = generated.get("erd") if isinstance(generated, dict) else None
    if not isinstance(erd, dict) and isinstance(generated, dict):
        if isinstance(generated.get("entities"), list):
            erd = generated

    if not isinstance(erd, dict):
        raise ValueError("LLM output is missing the erd object.")

    if not isinstance(erd.get("entities"), list):
        raise ValueError("ERD entities must be a JSON array.")

    if not isinstance(erd.get("relationships"), list):
        raise ValueError("ERD relationships must be a JSON array.")

    # Generate Mermaid ourselves instead of trusting model-generated Mermaid.
    # This ensures every entity is rendered as a table with its columns.
    mermaid = build_database_mermaid(erd)

    # Save the schema and generated Mermaid source.
    ERD_FILE.write_text(
        json.dumps(erd, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    MERMAID_FILE.write_text(
        mermaid.strip() + "\n",
        encoding="utf-8"
    )

    print(f"ERD JSON saved: {ERD_FILE}")
    print(f"LLM Mermaid source saved: {MERMAID_FILE}")
    print(f"Entities generated: {len(erd['entities'])}")
    print(
        "Relationships generated: "
        f"{len(erd['relationships'])}"
    )

    return erd, mermaid.strip()


# ============================================================
# 6. CLOUD RENDERING: MERMAID SOURCE TO PNG
# ============================================================

def render_mermaid_png(mermaid_text):
    """
    Send Mermaid source to Kroki's cloud API.

    No local Mermaid CLI and no Mermaid Ink.
    """

    print("\nSending Mermaid source to cloud renderer...")

    response = requests.post(
        KROKI_URL,
        data=mermaid_text.encode("utf-8"),
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Accept": "image/png"
        },
        timeout=(15, 120)
    )

    # Some proxy/server configurations can return an error status while the
    # response body is nevertheless a valid PNG. Check the PNG signature before
    # treating the HTTP status as a failure, and never print binary image bytes.
    png_signature = b"\x89PNG\r\n\x1a\n"
    is_png = response.content.startswith(png_signature)
    content_type = response.headers.get("Content-Type", "")

    if not is_png:
        body_preview = response.text[:1500] if response.content else "<empty response>"
        raise RuntimeError(
            "The cloud renderer did not return a valid PNG. "
            f"HTTP status: {response.status_code}; "
            f"Content-Type: {content_type}; response: {body_preview}"
        )

    # A valid PNG was returned, even if the server/proxy reported HTTP 500.
    if response.status_code != 200:
        print(
            f"Renderer returned HTTP {response.status_code}, "
            "but the response body is a valid PNG; saving it anyway."
        )

    PNG_FILE.write_bytes(response.content)

    print(f"ER diagram PNG saved: {PNG_FILE.resolve()}")
    print(f"PNG size: {PNG_FILE.stat().st_size:,} bytes")


# ============================================================
# 7. MAIN PIPELINE
# ============================================================

def main():
    # Reuse saved Jira data if available.
    hierarchy = load_hierarchy()

    if not hierarchy.get("epics"):
        raise RuntimeError(
            "No Epics found. Check the project key and Jira access."
        )

    print("\nGenerating ERD JSON and Mermaid using the LLM...")

    erd, mermaid_text = generate_erd_and_mermaid(hierarchy)

    print("\nRendering the LLM-generated Mermaid in the cloud...")

    render_mermaid_png(mermaid_text)

    print("\nPipeline completed successfully.")
    print(f"ERD JSON: {ERD_FILE.resolve()}")
    print(f"Mermaid source: {MERMAID_FILE.resolve()}")
    print(f"ERD PNG: {PNG_FILE.resolve()}")


if __name__ == "__main__":
    main()

