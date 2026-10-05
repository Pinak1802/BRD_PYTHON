import os
import json
import re
import subprocess
import time

from pathlib import Path
from urllib import request, error


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "system_design_output"
OUTPUT_DIR.mkdir(exist_ok=True)

JIRA_JSON = (
    BASE_DIR
    / "jira_erd_output"
    / "jira_epics_and_stories.json"
)

ERD_JSON = (
    BASE_DIR
    / "jira_erd_output"
    / "erd.json"
)

SYSTEM_DESIGN_JSON = (
    OUTPUT_DIR
    / "system_design.json"
)

SYSTEM_DESIGN_MERMAID = (
    OUTPUT_DIR
    / "system_design.mmd"
)
#todo

SYSTEM_DESIGN_PNG = ( OUTPUT_DIR / "system_design.png" )

# Existing generators
EPIC_STORY_GENERATOR = (
    BASE_DIR / "epic_story_uploader.py"
)

ERD_GENERATOR = (
    BASE_DIR / "stories_ERD.py"
)


# ============================================================
# LLM CONFIGURATION
# ============================================================

LLM_URL = os.getenv(
    "LLM_URL",
    # "https://api.apinex.bond/v1/chat/completions"
    # "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
    "http://localhost:11434/api/chat"
)

MODEL = os.getenv(
    "MODEL",
    "llama3.2:3b"
    # "qwen3:8b"
    # "free/gpt-6-luna"
    # "gemini-3.5-flash-lite"
)

API_KEY = os.getenv("LLM_API_KEY")


# ============================================================
# GENERAL HELPERS
# ============================================================

def print_section(title):

    print("\n")
    print("=" * 75)
    print(title)
    print("=" * 75)


def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def save_json(path, data):

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )


def clean_text(value):

    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# GENERATE EPIC/STORY JSON IF REQUIRED
# ============================================================

def ensure_jira_json():

    print_section("Epic / Story JSON")

    if JIRA_JSON.exists():

        print("Using existing file:")
        print(f"  {JIRA_JSON}")

        return True

    print(
        "jira_epics_and_stories.json was not found."
    )

    print(
        "Running existing epic/story generator..."
    )

    if not EPIC_STORY_GENERATOR.exists():

        print(
            "ERROR: epic_story_uploader.py was not found."
        )

        return False

    try:

        result = subprocess.run(
            [
                "python",
                str(EPIC_STORY_GENERATOR)
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True
        )

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:

            print(
                "Epic/story generator failed."
            )

            return False

    except Exception as exc:

        print(
            f"Unable to execute epic/story generator: {exc}"
        )

        return False

    if JIRA_JSON.exists():

        print(
            "Epic/story JSON generated successfully."
        )

        return True

    print(
        "Generator completed, but JSON file was not found."
    )

    return False


# ============================================================
# GENERATE ERD JSON IF REQUIRED
# ============================================================

def ensure_erd_json():

    print_section("ERD JSON")

    if ERD_JSON.exists():

        print("Using existing file:")
        print(f"  {ERD_JSON}")

        return True

    print(
        "erd.json was not found."
    )

    print(
        "Running existing ERD generator..."
    )

    if not ERD_GENERATOR.exists():

        print(
            "ERROR: stories_ERD.py was not found."
        )

        return False

    try:

        result = subprocess.run(
            [
                "python",
                str(ERD_GENERATOR)
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True
        )

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:

            print(
                "ERD generator failed."
            )

            return False

    except Exception as exc:

        print(
            f"Unable to execute ERD generator: {exc}"
        )

        return False

    if ERD_JSON.exists():

        print(
            "ERD JSON generated successfully."
        )

        return True

    print(
        "Generator completed, but erd.json was not found."
    )

    return False


# ============================================================
# JIRA DATA NORMALIZATION
# ============================================================

def shorten_text(text, max_chars=500):

    if not text:
        return ""

    text = str(text).strip()

    # Normalize whitespace
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    if len(text) <= max_chars:
        return text

    return text[:max_chars].rstrip() + "..."


def compact_acceptance_criteria(criteria):

    if not criteria:
        return []

    result = []

    if isinstance(criteria, str):

        criteria = [
            criteria
        ]

    if not isinstance(criteria, list):
        return result

    for item in criteria:

        if isinstance(item, str):

            value = item

        elif isinstance(item, dict):

            value = (
                item.get("criterion")
                or item.get("description")
                or item.get("text")
                or ""
            )

        else:

            continue

        value = shorten_text(
            value,
            250
        )

        if value:
            result.append(value)

    # Don't send excessive criteria
    return result[:5]


def extract_epics_and_stories(data):

    """
    Creates a compact architectural representation.

    The system-design LLM does not need all Jira metadata.
    It mainly needs:

        Epic
        Story
        Description
        Acceptance Criteria
    """

    result = []

    if isinstance(data, dict):

        epics = (
            data.get("epics")
            or data.get("data")
            or data.get("items")
            or []
        )

    elif isinstance(data, list):

        epics = data

    else:

        epics = []

    for epic in epics:

        if not isinstance(
            epic,
            dict
        ):
            continue

        epic_name = (
            epic.get("summary")
            or epic.get("name")
            or epic.get("title")
            or "Unnamed Epic"
        )

        epic_key = (
            epic.get("key")
            or epic.get("id")
            or ""
        )

        stories = (
            epic.get("stories")
            or epic.get("issues")
            or epic.get("children")
            or []
        )

        compact_stories = []

        for story in stories:

            if not isinstance(
                story,
                dict
            ):
                continue

            summary = (
                story.get("summary")
                or story.get("title")
                or story.get("name")
                or ""
            )

            description = (
                story.get("description")
                or ""
            )

            acceptance = (
                story.get(
                    "acceptanceCriteria"
                )
                or story.get(
                    "acceptance_criteria"
                )
                or story.get(
                    "acceptanceCriteriaList"
                )
                or []
            )

            compact_story = {
                "key": str(
                    story.get("key")
                    or story.get("id")
                    or ""
                ),

                "summary": shorten_text(
                    summary,
                    200
                ),

                "description": shorten_text(
                    description,
                    400
                ),

                "acceptanceCriteria":
                    compact_acceptance_criteria(
                        acceptance
                    )
            }

            compact_stories.append(
                compact_story
            )

        result.append({
            "key": str(epic_key),

            "name": shorten_text(
                epic_name,
                150
            ),

            "stories": compact_stories
        })

    return result



# ============================================================
# ERD DATA NORMALIZATION
# ============================================================

def extract_erd_information(data):

    entities = []
    relationships = []

    if isinstance(data, dict):

        raw_entities = (
            data.get("entities")
            or data.get("tables")
            or data.get("models")
            or []
        )

        raw_relationships = (
            data.get("relationships")
            or data.get("relations")
            or data.get("associations")
            or []
        )

    elif isinstance(data, list):

        raw_entities = data
        raw_relationships = []

    else:

        raw_entities = []
        raw_relationships = []

    # ========================================================
    # ENTITIES
    # ========================================================

    for entity in raw_entities:

        if isinstance(
            entity,
            str
        ):

            entities.append({
                "name": entity
            })

            continue

        if not isinstance(
            entity,
            dict
        ):
            continue

        name = (
            entity.get("name")
            or entity.get("entity")
            or entity.get("table")
            or entity.get("title")
        )

        if not name:
            continue

        attributes = (
            entity.get("attributes")
            or entity.get("fields")
            or entity.get("columns")
            or []
        )

        attribute_names = []

        if isinstance(
            attributes,
            list
        ):

            for attribute in attributes:

                if isinstance(
                    attribute,
                    str
                ):

                    attribute_names.append(
                        attribute
                    )

                elif isinstance(
                    attribute,
                    dict
                ):

                    attribute_name = (
                        attribute.get("name")
                        or attribute.get("field")
                        or attribute.get("column")
                    )

                    if attribute_name:

                        attribute_names.append(
                            attribute_name
                        )

        entities.append({
            "name": str(name),
            "attributes": attribute_names[:20]
        })

    # ========================================================
    # RELATIONSHIPS
    # ========================================================

    for relationship in raw_relationships:

        if isinstance(
            relationship,
            str
        ):

            relationships.append(
                relationship
            )

            continue

        if not isinstance(
            relationship,
            dict
        ):
            continue

        source = (
            relationship.get("from")
            or relationship.get("source")
            or relationship.get("entity1")
            or ""
        )

        target = (
            relationship.get("to")
            or relationship.get("target")
            or relationship.get("entity2")
            or ""
        )

        relationship_type = (
            relationship.get("type")
            or relationship.get("cardinality")
            or ""
        )

        relationships.append({
            "from": str(source),
            "to": str(target),
            "type": str(relationship_type)
        })

    return {
        "entities": entities,
        "relationships": relationships
    }



# ============================================================
# COMPACT INPUT
# ============================================================

def build_compact_input(jira_data, erd_data):

    jira_information = extract_epics_and_stories(
        jira_data
    )

    erd_information = extract_erd_information(
        erd_data
    )

    return {
        "jira": {
            "epics": jira_information
        },

        "erd": erd_information
    }


# ============================================================
# LLM PROMPT
# ============================================================

def build_system_design_prompt(compact_input):

    input_text = json.dumps(
        compact_input,
        indent=2,
        ensure_ascii=False
    )
    jira_text = json.dumps(
        compact_input["jira"],
        indent=2,
        ensure_ascii=False
    )

    erd_text = json.dumps(
        compact_input["erd"],
        indent=2,
        ensure_ascii=False
    )

    prompt = f'''You are a Senior Solution Architect and Enterprise Application Architect.

Your task is to design a complete, production-oriented SYSTEM DESIGN for the software system described by the provided Jira Epics, Jira Stories, and ERD.

The Jira Epics and Stories represent the functional business requirements.
The ERD represents the persistent data model.
Your responsibility is to transform these requirements into a coherent technical architecture.

IMPORTANT:

* Do NOT merely summarize the Jira stories.
* Do NOT copy Jira story descriptions or acceptance criteria verbatim.
* Do NOT invent business requirements that are not supported by the input.
* You MAY introduce necessary technical components such as API layers, authentication, authorization, validation, service layers, repositories, transaction boundaries, logging, monitoring, caching, messaging, and deployment components when they are architecturally justified.
* Every major functional capability must be traceable back to Jira requirements.
* Database entities and relationships must remain consistent with the supplied ERD.
* Prefer a modular, maintainable architecture suitable for enterprise implementation.
* Make reasonable architectural decisions where the requirements do not explicitly specify implementation details, but clearly state those decisions.

INPUT 1: JIRA EPICS AND STORIES
{jira_text}

INPUT 2: ERD
{erd_text}

Based on these inputs, generate the SYSTEM DESIGN using the following structure.

Return ONLY valid JSON.
Do not return Markdown.
Do not add explanations before or after the JSON.

{{
"systemOverview": {{
"systemName": "",
"purpose": "",
"architectureStyle": "",
"architecturalRationale": "",
"description": ""
}},

"actors": [
{{
"name": "",
"responsibility": "",
"interactions": []
}}
],

"architecture": {{
"components": [
{{
"name": "",
"type": "",
"responsibility": "",
"whyItExists": "",
"dependencies": [],
"ownedData": [],
"operations": []
}}
],
"communicationPatterns": []
}},

"functionalModules": [
{{
"name": "",
"purpose": "",
"jiraEpics": [],
"jiraStories": [],
"responsibilities": [],
"erdEntities": []
}}
],

"apis": [
{{
"method": "",
"endpoint": "",
"purpose": "",
"module": "",
"request": "",
"response": "",
"authentication": "",
"authorization": "",
"validation": [],
"errors": []
}}
],

"businessFlows": [
{{
"name": "",
"actor": "",
"steps": [],
"components": [],
"validations": [],
"databaseOperations": [],
"result": ""
}}
],

"dataFlows": [
{{
"name": "",
"steps": [],
"dataEntities": [],
"consistency": ""
}}
],

"databaseDesign": {{
"entities": [
{{
"name": "",
"purpose": "",
"keyAttributes": [],
"owningModule": ""
}}
],
"relationships": [],
"transactions": [],
"integrityConstraints": [],
"indexes": []
}},

"security": {{
"authentication": "",
"authorization": "",
"roles": [],
"credentialProtection": "",
"tokenManagement": "",
"apiSecurity": [],
"dataProtection": []
}},

"errorHandling": [
{{
"failure": "",
"detection": "",
"response": "",
"recovery": ""
}}
],

"nonFunctionalArchitecture": {{
"performance": [],
"scalability": [],
"availability": [],
"reliability": [],
"maintainability": [],
"observability": []
}},

"deploymentArchitecture": {{
"components": [],
"environments": [],
"communication": []
}},

"traceability": [
{{
"jiraEpic": "",
"jiraStory": "",
"module": "",
"api": "",
"erdEntities": []
}}
],

"architecturalDecisions": [
{{
"decision": "",
"rationale": "",
"consequence": ""
}}
],

"implementationSequence": []
}}


ARCHITECTURAL RULES

1. SYSTEM OVERVIEW

Identify:

* What the system does.
* Its primary business purpose.
* The recommended architecture style.
* Why that architecture fits the requirements.
* The major architectural characteristics.

Choose an architecture style based on the requirements, such as:

* Modular monolith
* Layered architecture
* Microservices
* Event-driven architecture
* Hybrid architecture

Do not choose microservices merely because it is common.
Choose the simplest architecture that adequately satisfies the requirements.

2. ACTORS

Identify only meaningful actors supported by the requirements.

Examples:

* Student
* Administrator
* Librarian
* External system
* System scheduler

For each actor, explain what they actually do in the system.

3. ARCHITECTURE COMPONENTS

Identify the major technical components required to implement the system.

Typical components may include:

* Web / Mobile Client
* API Gateway
* Authentication Module
* User Management Module
* Business/Application Services
* Domain Modules
* Validation Layer
* Repository/Data Access Layer
* Database
* Cache
* Message Broker
* Notification Service
* External Integrations
* Logging/Monitoring

Only include components that are justified by the requirements.

For every component specify:

* responsibility
* reason for existence
* dependencies
* owned data
* important operations

Do not create a separate component for every Jira story.

Group related stories into meaningful business modules.

4. FUNCTIONAL MODULES

Convert Jira Epics and related Stories into logical application modules.

For example:

Authentication
Student Management
Book Catalog
Book Borrowing
Book Return
Administration
Notification

Each module should contain:

* purpose
* related Jira Epics
* related Jira Stories
* responsibilities
* ERD entities used by the module

A module should represent a meaningful business capability rather than a single API.

5. API DESIGN

Derive the most important REST APIs required by the system.

For each API provide:

* HTTP method
* endpoint
* purpose
* owning module
* request
* response
* authentication requirement
* authorization requirement
* validation
* possible errors

Use realistic REST conventions.

Do not create unnecessary APIs for every internal operation.

6. BUSINESS FLOWS

Describe the most important end-to-end business processes.

Examples:

User Registration/Login
Book Search
Book Borrowing
Book Return
Administrative Book Management

For each flow explain:

Actor
→ API/UI
→ Application Module
→ Business Validation
→ Database Operation
→ Result

Include important business rules.

For example, if the requirements state that a student can acquire at most 3 books, the borrowing flow must explicitly show:

1. Identify student.
2. Check current active borrowing count.
3. Validate the maximum borrowing limit.
4. Check book availability.
5. Create borrowing transaction.
6. Update book availability.
7. Return successful result.

Do not invent business rules not supported by the input.

7. DATA FLOWS

Explain how important information moves through the system.

Example:

Client
→ API
→ Authentication
→ Application Service
→ Validation
→ Repository
→ Database
→ Response

For each important flow identify:

* participating components
* data entities
* consistency requirements

8. DATABASE DESIGN

Use the supplied ERD as the authoritative source for persistent entities and relationships.

Do not contradict the ERD.

For every important entity identify:

* purpose
* key attributes
* owning module

Also describe:

* relationships
* transaction boundaries
* integrity constraints
* useful indexes

Do not invent attributes unless they are technically necessary and clearly justified.

9. SECURITY

Design security appropriate for the system.

Consider:

* authentication
* authorization
* roles
* password hashing
* token management
* API protection
* input validation
* sensitive data protection
* least privilege
* audit logging where appropriate

Do not claim a specific security technology unless supported by the requirements or clearly state it as an architectural decision.

10. ERROR HANDLING

Identify important failure scenarios.

Examples:

* Invalid credentials
* Unauthorized access
* Resource not found
* Validation failure
* Business rule violation
* Duplicate data
* Database failure
* External service failure
* Timeout
* Unexpected application error

For each explain:

* how failure is detected
* API/system response
* recovery or handling strategy

11. NON-FUNCTIONAL ARCHITECTURE

Provide realistic considerations for:

Performance
Scalability
Availability
Reliability
Maintainability
Observability

Do not use generic statements such as "the system should be fast."

Explain the architectural mechanism where appropriate.

Example:

"Database indexes should be created on frequently queried attributes such as student identifier and book identifier to reduce lookup latency."

12. DEPLOYMENT ARCHITECTURE

Describe how the system would be deployed.

Include logical deployment components such as:

Client
API/Application Server
Database
Cache
Message Broker
External Services
Monitoring

Do not invent cloud-specific infrastructure unless required.

Keep the deployment architecture implementation-neutral where possible.

13. TRACEABILITY

Create explicit traceability between:

Jira Epic
→ Jira Story
→ Functional Module
→ API
→ ERD Entity

Every important business capability should be traceable.

Do not lose Jira story identifiers.

14. ARCHITECTURAL DECISIONS

Identify the most important architectural decisions.

For example:

* Why modular monolith instead of microservices?
* Why REST APIs?
* Why centralized authentication?
* Why transactional borrowing operation?
* Why database indexing?
* Why asynchronous processing for notifications?

For every decision explain:

* decision
* rationale
* consequence/trade-off

Keep this focused on meaningful architectural decisions.

15. IMPLEMENTATION SEQUENCE

Provide a logical implementation order.

Example:

1. Database schema
2. Authentication and authorization
3. Core domain modules
4. Repository/data access
5. REST APIs
6. Business workflows
7. External integrations
8. Error handling
9. Observability
10. Deployment

Adapt the sequence to the actual system.

QUALITY REQUIREMENTS

The generated design must be:

* Architecturally coherent.
* Internally consistent.
* Traceable to Jira.
* Consistent with the ERD.
* Implementation-oriented.
* Suitable for a senior architect/business analyst presentation.
* Detailed enough to guide developers.
* Concise enough to remain readable.

Avoid:

* Generic filler.
* Repeating Jira stories.
* Repeating the ERD without architectural interpretation.
* Creating unnecessary microservices.
* Inventing unsupported business functionality.
* Excessive technical jargon.
* Long paragraphs.

OUTPUT SIZE GUIDELINES

Keep the response focused.

* systemOverview descriptions: maximum 2–3 sentences.
* Component responsibilities: maximum 2–3 sentences.
* Business flow: maximum 8 steps.
* Architectural decisions: maximum 3 sentences each.
* API descriptions: concise.
* Do not duplicate the same information across sections.

The final output must be valid JSON and must contain no Markdown or explanatory text outside the JSON.'''



    return prompt


# ============================================================
# LLM CALL
# ============================================================

#todo ollama


# ============================================================
# OLLAMA LOCAL LLM CALL
# ============================================================

def call_llm(prompt):

    payload = {
        "model": MODEL,

        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a senior enterprise software "
                    "architect. Produce precise, structured "
                    "architecture models. Return valid JSON only."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        # Ask Ollama to return a JSON object.
        "format": "json",

        # Wait for the complete response.
        "stream": False,

        "options": {
            "temperature": 0.15,
            "num_ctx": 16384,
            "num_predict": 8192
        }
    }

    data = json.dumps(
        payload
    ).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    req = request.Request(
        LLM_URL,
        data=data,
        headers=headers,
        method="POST"
    )

    print("Sending system-design request to Ollama...")
    print(f"Local model: {MODEL}")
    print(f"Ollama URL: {LLM_URL}")

    try:

        with request.urlopen(
            req,
            timeout=600
        ) as response:

            body = response.read().decode(
                "utf-8",
                errors="replace"
            )

            result = json.loads(body)

            # Ollama's /api/chat response format.
            content = (
                result
                .get("message", {})
                .get("content", "")
            )

            if not content.strip():

                raise RuntimeError(
                    "Ollama returned an empty response. "
                    "Check whether the model completed generation."
                )

            print("Ollama response received successfully.")

            return content

    except error.HTTPError as exc:

        body = exc.read().decode(
            "utf-8",
            errors="replace"
        )

        raise RuntimeError(
            f"Ollama HTTP error {exc.code}: {body}"
        ) from exc

    except error.URLError as exc:

        raise RuntimeError(
            "Cannot connect to Ollama at "
            f"{LLM_URL}. Make sure Ollama is running."
        ) from exc

    except (json.JSONDecodeError, KeyError) as exc:

        raise RuntimeError(
            f"Unable to parse Ollama response: {exc}"
        ) from exc


#todo OPEN_AI

# def call_llm(prompt):
#
#     if not API_KEY:
#
#         raise RuntimeError(
#             "API_KEY environment variable is not set."
#         )
#
#     payload = {
#         "model": MODEL,
#
#         "messages": [
#             {
#                 "role": "system",
#                 "content": (
#                     "You are a senior enterprise software "
#                     "architect. Produce precise, structured "
#                     "architecture models."
#                 )
#             },
#
#             {
#                 "role": "user",
#                 "content": prompt
#             }
#         ],
#
#         "temperature": 0.15
#     }
#
#     data = json.dumps(
#         payload
#     ).encode("utf-8")
#
#     headers = {
#         "Content-Type": "application/json",
#         "Authorization": f"Bearer {API_KEY}",
#         "Accept": "application/json",
#         "User-Agent": "Mozilla/5.0"
#     }
#
#     req = request.Request(
#         LLM_URL,
#         data=data,
#         headers=headers,
#         method="POST"
#     )
#
#     print(
#         "Sending system-design request to LLM..."
#     )
#
#     try:
#
#         with request.urlopen(
#             req,
#             timeout=125
#         ) as response:
#
#             status = response.status
#
#             print(
#                 f"LLM HTTP status: {status}"
#             )
#
#             body = response.read().decode(
#                 "utf-8",
#                 errors="replace"
#             )
#
#             result = json.loads(body)
#
#             return (
#                 result["choices"][0]
#                 ["message"]
#                 ["content"]
#             )
#
#     except error.HTTPError as exc:
#
#         body = exc.read().decode(
#             "utf-8",
#             errors="replace"
#         )
#
#         print(
#             f"HTTP error {exc.code}: {body}"
#         )
#
#         # ----------------------------------------------------
#         # Cloudflare timeout
#         # ----------------------------------------------------
#
#         if exc.code == 524:
#
#             raise RuntimeError(
#                 "The LLM request exceeded the Cloudflare "
#                 "proxy timeout. The request is still too "
#                 "large or the model is taking too long."
#             )
#
#         # ----------------------------------------------------
#         # Access denied
#         # ----------------------------------------------------
#
#         if exc.code == 403:
#
#             raise RuntimeError(
#                 "The LLM endpoint rejected the request "
#                 "with HTTP 403."
#             )
#
#         raise RuntimeError(
#             f"LLM HTTP error: {exc.code}"
#         )
#
#     except Exception as exc:
#
#         raise RuntimeError(
#             f"LLM request failed: {exc}"
#         )

#todo GEMINI

# def call_llm(prompt):
#
#     if not API_KEY:
#
#         raise RuntimeError(
#             "GEMINI_API_KEY environment variable is not set."
#         )
#
#     # --------------------------------------------------------
#     # Gemini request body
#     # --------------------------------------------------------
#
#     payload = {
#         "contents": [
#             {
#                 "parts": [
#                     {
#                         "text": prompt
#                     }
#                 ]
#             }
#         ],
#
#         "generationConfig": {
#             "temperature": 0.15,
#             "responseMimeType": "application/json"
#             }
#     }
#
#     data = json.dumps(
#         payload
#     ).encode("utf-8")
#
#     # --------------------------------------------------------
#     # Gemini authentication
#     # --------------------------------------------------------
#
#     headers = {
#         "Content-Type": "application/json",
#         "x-goog-api-key": API_KEY,
#         "Accept": "application/json",
#         "User-Agent": "Mozilla/5.0"
#     }
#
#     req = request.Request(
#         LLM_URL,
#         data=data,
#         headers=headers,
#         method="POST"
#     )
#
#     print(
#         "Sending system-design request to Gemini..."
#     )
#
#     try:
#
#         with request.urlopen(
#             req,
#             timeout=125
#         ) as response:
#
#             status = response.status
#
#             print(
#                 f"Gemini HTTP status: {status}"
#             )
#
#             body = response.read().decode(
#                 "utf-8",
#                 errors="replace"
#             )
#
#             result = json.loads(
#                 body
#             )
#
#             # ------------------------------------------------
#             # Extract Gemini generated text
#             # ------------------------------------------------
#
#             return (
#                 result["candidates"][0]
#                 ["content"]
#                 ["parts"][0]
#                 ["text"]
#             )
#
#     except error.HTTPError as exc:
#
#         body = exc.read().decode(
#             "utf-8",
#             errors="replace"
#         )
#
#         print(
#             f"Gemini HTTP error {exc.code}: {body}"
#         )
#
#         if exc.code == 400:
#
#             raise RuntimeError(
#                 "Gemini rejected the request with HTTP 400.\n"
#                 + body
#             )
#
#         if exc.code == 401:
#
#             raise RuntimeError(
#                 "Gemini API authentication failed.\n"
#                 "Check GEMINI_API_KEY."
#             )
#
#         if exc.code == 403:
#
#             raise RuntimeError(
#                 "Gemini API access was denied.\n"
#                 + body
#             )
#
#         if exc.code == 404:
#
#             raise RuntimeError(
#                 "Gemini model or endpoint was not found.\n"
#                 + body
#             )
#
#         if exc.code == 429:
#
#             raise RuntimeError(
#                 "Gemini API rate limit/quota exceeded.\n"
#                 + body
#             )
#
#         raise RuntimeError(
#             f"Gemini HTTP error: {exc.code}\n"
#             + body
#         )
#
#     except Exception as exc:
#
#         raise RuntimeError(
#             f"Gemini request failed: {exc}"
#         )


# ============================================================
# EXTRACT JSON FROM LLM
# ============================================================
def extract_json(text):

    # --------------------------------------------------------
    # SAVE COMPLETE RAW RESPONSE
    # --------------------------------------------------------

    raw_output_file = (
        OUTPUT_DIR
        / "system_design_raw.txt"
    )

    with open(
        raw_output_file,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            text
        )

    print(
        "\nRaw LLM response saved:"
    )

    print(
        f"  {raw_output_file}"
    )

    # --------------------------------------------------------
    # CLEAN RESPONSE
    # --------------------------------------------------------

    text = text.strip()

    # Remove ```json
    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    # Remove ```
    text = re.sub(
        r"^```\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    text = text.strip()

    # --------------------------------------------------------
    # PRINT RESPONSE PREVIEW
    # --------------------------------------------------------

    print(
        "\nLLM response preview:"
    )

    print(
        "-" * 75
    )

    print(
        text[:3000]
    )

    print(
        "-" * 75
    )

    # --------------------------------------------------------
    # TRY DIRECT JSON
    # --------------------------------------------------------

    try:

        return json.loads(
            text
        )

    except json.JSONDecodeError as exc:

        print(
            "\nDirect JSON parsing failed:"
        )

        print(
            f"  {exc}"
        )

    # --------------------------------------------------------
    # FIND JSON OBJECT
    # --------------------------------------------------------

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:

        raise ValueError(
            "LLM response does not contain "
            "a JSON object."
        )

    json_text = text[
        start:end + 1
    ]

    # --------------------------------------------------------
    # TRY EXTRACTED JSON
    # --------------------------------------------------------

    try:

        return json.loads(
            json_text
        )

    except json.JSONDecodeError as exc:

        print(
            "\nJSON parsing failed."
        )

        print(
            f"Error: {exc}"
        )

        print(
            f"Error position: {exc.pos}"
        )

        # ----------------------------------------------------
        # SHOW AREA AROUND ERROR
        # ----------------------------------------------------

        error_start = max(
            0,
            exc.pos - 500
        )

        error_end = min(
            len(json_text),
            exc.pos + 1000
        )

        print(
            "\nProblematic response area:"
        )

        print(
            "-" * 75
        )

        print(
            json_text[
                error_start:error_end
            ]
        )

        print(
            "-" * 75
        )

        raise ValueError(
            "LLM returned invalid JSON. "
            "Check system_design_raw.txt "
            "for the complete response."
        )



# ============================================================
# VALIDATE SYSTEM DESIGN
# ============================================================

def validate_system_design(data):

    required_sections = [
        "systemOverview",
        "actors",
        "architecture",
        "functionalModules",
        "apis",
        "businessFlows",
        "dataFlows",
        "databaseDesign",
        "security",
        "errorHandling",
        "nonFunctionalArchitecture",
        "deploymentArchitecture",
        "traceability",
        "architecturalDecisions",
        "implementationSequence"
    ]

    missing = []

    for section in required_sections:

        if section not in data:

            missing.append(section)

    if missing:

        raise ValueError(
            "System design JSON is missing sections: "
            + ", ".join(missing)
        )

    return True


# ============================================================
# GENERATE SYSTEM DESIGN
# ============================================================

def generate_system_design(
    jira_data,
    erd_data
):

    print_section(
        "Preparing System Design Input"
    )

    compact_input = build_compact_input(
        jira_data,
        erd_data
    )

    epic_count = len(
        compact_input["jira"]["epics"]
    )

    entity_count = len(
        compact_input["erd"]["entities"]
    )

    relationship_count = len(
        compact_input["erd"]["relationships"]
    )

    story_count = sum(
        len(epic["stories"])
        for epic
        in compact_input["jira"]["epics"]
    )

    print(
        f"Epics: {epic_count}"
    )

    print(
        f"Stories: {story_count}"
    )

    print(
        f"ERD entities: {entity_count}"
    )

    print(
        f"ERD relationships: {relationship_count}"
    )

    prompt = build_system_design_prompt(
        compact_input
    )

    print(
        f"\nPrompt size: {len(prompt)} characters"
    )

    print_section(
        "Generating System Design"
    )

    response = call_llm(
        prompt
    )

    print(
        "LLM response received."
    )

    system_design = extract_json(
        response
    )

    validate_system_design(
        system_design
    )

    save_json(
        SYSTEM_DESIGN_JSON,
        system_design
    )

    print(
        "\nSystem design JSON saved:"
    )

    print(
        f"  {SYSTEM_DESIGN_JSON}"
    )

    return system_design


# ============================================================
# MERMAID HELPERS
# ============================================================

def safe_id(text, prefix):

    value = re.sub(
        r"[^a-zA-Z0-9_]",
        "_",
        str(text)
    )

    value = value.strip("_")

    if not value:

        value = "Component"

    return (
        prefix
        + "_"
        + value[:30]
    )


def mermaid_text(text):

    text = clean_text(text)

    text = text.replace(
        '"',
        "'"
    )

    text = text.replace(
        "\n",
        " "
    )

    return text


# ============================================================
# GENERATE ENTERPRISE SYSTEM DESIGN MERMAID
# ============================================================

def generate_mermaid(system_design):

    print_section(
        "Generating System Design Mermaid"
    )

    lines = []

    lines.append(
        "%%{init: {'theme': 'base', 'flowchart': {'htmlLabels': true, 'curve': 'basis', 'nodeSpacing': 80, 'rankSpacing': 100}, 'themeVariables': {'fontSize': '20px', 'fontFamily': 'Arial'}}}%%"
    )

    lines.append(
        "flowchart TB"
    )

    lines.append("")

    # ========================================================
    # CLIENT LAYER
    # ========================================================

    lines.append(
        '    subgraph CLIENT["Client Layer"]'
    )

    actor_ids = []

    for index, actor in enumerate(
        system_design.get(
            "actors",
            []
        )
    ):

        if not isinstance(
            actor,
            dict
        ):
            continue

        name = actor.get(
            "name",
            f"Actor {index + 1}"
        )

        actor_id = f"ACTOR_{index + 1}"

        actor_ids.append(
            actor_id
        )

        lines.append(
            f'        {actor_id}["{mermaid_text(name)}"]'
        )

    lines.append(
        "    end"
    )

    lines.append("")

    # ========================================================
    # APPLICATION / ARCHITECTURE LAYER
    # ========================================================

    lines.append(
        '    subgraph APPLICATION["Application Layer"]'
    )

    components = (
        system_design
        .get("architecture", {})
        .get("components", [])
    )

    component_map = {}

    for index, component in enumerate(
        components
    ):

        if not isinstance(
            component,
            dict
        ):
            continue

        name = component.get(
            "name",
            f"Component {index + 1}"
        )

        component_id = (
            f"COMP_{index + 1}"
        )

        component_map[
            name.lower()
        ] = component_id

        responsibility = component.get(
            "responsibility",
            ""
        )

        label = (
            f"{name}"
        )

        if responsibility:
            label += (
                f"<br/><span style='font-size:16px'>"
                f"{responsibility[:80]}"
                f"</span>"
            )

        lines.append(
            f'        {component_id}["'
            f'{mermaid_text(label)}'
            f'"]'
        )

    lines.append(
        "    end"
    )

    lines.append("")

    # ========================================================
    # DATABASE LAYER
    # ========================================================

    lines.append(
        '    subgraph DATABASE["Data Layer"]'
    )

    entities = (
        system_design
        .get("databaseDesign", {})
        .get("entities", [])
    )

    entity_map = {}

    for index, entity in enumerate(
        entities
    ):

        if not isinstance(
            entity,
            dict
        ):
            continue

        name = entity.get(
            "name",
            f"Entity {index + 1}"
        )

        entity_id = (
            f"DB_{index + 1}"
        )

        entity_map[
            name.lower()
        ] = entity_id

        lines.append(
            f'        {entity_id}['
            f'"{mermaid_text(name)}"'
            f']'
        )

    lines.append(
        "    end"
    )

    lines.append("")

    # ========================================================
    # EXTERNAL / DEPLOYMENT LAYER
    # ========================================================

    deployment = system_design.get(
        "deploymentArchitecture",
        {}
    )

    deployment_components = (
        deployment.get(
            "components",
            []
        )
    )

    if deployment_components:

        lines.append(
            '    subgraph INFRA["Infrastructure / External Layer"]'
        )

        for index, component in enumerate(
            deployment_components
        ):

            infra_id = (
                f"INFRA_{index + 1}"
            )

            lines.append(
                f'        {infra_id}['
                f'"{mermaid_text(component)}"'
                f']'
            )

        lines.append(
            "    end"
        )

        lines.append("")

    # ========================================================
    # ACTOR → APPLICATION
    # ========================================================

    if actor_ids and component_map:

        first_component = next(
            iter(component_map.values())
        )

        for actor_id in actor_ids:

            lines.append(
                f"    {actor_id} --> "
                f"{first_component}"
            )

    # ========================================================
    # COMPONENT DEPENDENCIES
    # ========================================================

    for index, component in enumerate(
        components
    ):

        if not isinstance(
            component,
            dict
        ):
            continue

        source_id = (
            f"COMP_{index + 1}"
        )

        dependencies = component.get(
            "dependencies",
            []
        )

        if isinstance(
            dependencies,
            str
        ):

            dependencies = [
                dependencies
            ]

        for dependency in dependencies:

            target = component_map.get(
                clean_text(
                    dependency
                ).lower()
            )

            if target:

                lines.append(
                    f"    {source_id} --> {target}"
                )

    # ========================================================
    # COMPONENT → DATABASE
    # ========================================================

    for index, component in enumerate(
        components
    ):

        if not isinstance(
            component,
            dict
        ):
            continue

        source_id = (
            f"COMP_{index + 1}"
        )

        owned_data = component.get(
            "ownedData",
            []
        )

        if isinstance(
            owned_data,
            str
        ):

            owned_data = [
                owned_data
            ]

        for data_name in owned_data:

            target = entity_map.get(
                clean_text(
                    data_name
                ).lower()
            )

            if target:

                lines.append(
                    f"    {source_id} --> {target}"
                )

    # ========================================================
    # ERD RELATIONSHIPS
    # ========================================================

    relationships = (
        system_design
        .get("databaseDesign", {})
        .get("relationships", [])
    )

    for relationship in relationships:

        if not isinstance(
            relationship,
            dict
        ):
            continue

        source = clean_text(
            relationship.get(
                "from"
            )
        ).lower()

        target = clean_text(
            relationship.get(
                "to"
            )
        ).lower()

        source_id = entity_map.get(
            source
        )

        target_id = entity_map.get(
            target
        )

        if source_id and target_id:

            lines.append(
                f"    {source_id} -.-> "
                f"{target_id}"
            )

    # ========================================================
    # STYLING
    # ========================================================

    lines.append("")

    lines.append(
        "    classDef actor fill:#e8f0fe,stroke:#333"
    )

    lines.append(
        "    classDef component fill:#e8f5e9,stroke:#333"
    )

    lines.append(
        "    classDef database fill:#fff3e0,stroke:#333"
    )

    lines.append(
        "    classDef infra fill:#f3e5f5,stroke:#333"
    )

    lines.append("")

    # Actor class
    for actor_id in actor_ids:

        lines.append(
            f"    class {actor_id} actor"
        )

    # Component class
    for component_id in component_map.values():

        lines.append(
            f"    class {component_id} component"
        )

    # Database class
    for entity_id in entity_map.values():

        lines.append(
            f"    class {entity_id} database"
        )

    mermaid = "\n".join(
        lines
    )

    with open(
        SYSTEM_DESIGN_MERMAID,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            mermaid
        )

    print(
        "System design Mermaid saved:"
    )

    print(
        f"  {SYSTEM_DESIGN_MERMAID}"
    )

    return mermaid

#todo .png function added...

# ============================================================
# GENERATE SYSTEM DESIGN PNG
# ============================================================

def generate_system_design_png():

    print_section(
        "Generating System Design PNG"
    )

    if not SYSTEM_DESIGN_MERMAID.exists():

        raise RuntimeError(
            "System design Mermaid file was not found."
        )

    command = [
        "mmdc.cmd",
        "-i",
        str(SYSTEM_DESIGN_MERMAID),
        "-o",
        str(SYSTEM_DESIGN_PNG),
        "-b",
        "white"
    ]

    print(
        "Rendering Mermaid diagram to PNG..."
    )

    try:

        result = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True
        )

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:

            raise RuntimeError(
                "Mermaid PNG generation failed:\n"
                + result.stderr
            )

    except FileNotFoundError:

        raise RuntimeError(
            "Mermaid CLI 'mmdc' was not found.\n\n"
            "Install it using:\n"
            "npm install -g @mermaid-js/mermaid-cli\n\n"
            "Then verify with:\n"
            "mmdc --version"
        )

    if not SYSTEM_DESIGN_PNG.exists():

        raise RuntimeError(
            "Mermaid CLI completed, but "
            "system_design.png was not created."
        )

    print(
        "\nSystem design PNG saved:"
    )

    print(
        f"  {SYSTEM_DESIGN_PNG}"
    )

    return SYSTEM_DESIGN_PNG

# ============================================================
# SUMMARY
# ============================================================

def print_summary(system_design):

    overview = system_design.get(
        "systemOverview",
        {}
    )

    architecture = system_design.get(
        "architecture",
        {}
    )

    modules = system_design.get(
        "functionalModules",
        []
    )

    apis = system_design.get(
        "apis",
        []
    )

    flows = system_design.get(
        "businessFlows",
        []
    )

    entities = (
        system_design
        .get("databaseDesign", {})
        .get("entities", [])
    )

    print_section(
        "SYSTEM DESIGN SUMMARY"
    )

    print(
        f"System:"
        f" {overview.get('systemName', '')}"
    )

    print(
        f"Architecture:"
        f" {overview.get('architectureStyle', '')}"
    )

    print(
        f"Components:"
        f" {len(architecture.get('components', []))}"
    )

    print(
        f"Functional modules:"
        f" {len(modules)}"
    )

    print(
        f"APIs:"
        f" {len(apis)}"
    )

    print(
        f"Business flows:"
        f" {len(flows)}"
    )

    print(
        f"Database entities:"
        f" {len(entities)}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print_section(
        "AI SYSTEM DESIGN GENERATOR"
    )

    # --------------------------------------------------------
    # STEP 1
    # --------------------------------------------------------

    if not ensure_jira_json():

        raise RuntimeError(
            "Unable to obtain Jira Epic/Story JSON."
        )

    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    if not ensure_erd_json():

        raise RuntimeError(
            "Unable to obtain ERD JSON."
        )

    # --------------------------------------------------------
    # STEP 3
    # --------------------------------------------------------

    print_section(
        "Loading Inputs"
    )

    jira_data = load_json(
        JIRA_JSON
    )

    erd_data = load_json(
        ERD_JSON
    )

    print(
        "Loaded Jira hierarchy from:"
    )

    print(
        f"  {JIRA_JSON}"
    )

    print(
        "\nLoaded ERD from:"
    )

    print(
        f"  {ERD_JSON}"
    )

    # --------------------------------------------------------
    # STEP 4
    # --------------------------------------------------------

    system_design = generate_system_design(
        jira_data,
        erd_data
    )

    # --------------------------------------------------------
    # STEP 5
    # --------------------------------------------------------

    generate_mermaid(
        system_design
    )

    # --------------------------------------------------------
    # STEP 6
    # --------------------------------------------------------
    #todo pinak

    # print("Pinak Ranjan Das")
    generate_system_design_png()

    print_summary(
        system_design
    )

    # --------------------------------------------------------
    # COMPLETE
    # --------------------------------------------------------

    print_section(
        "SYSTEM DESIGN COMPLETE"
    )

    print(
        "Generated artifacts:"
    )

    print(
        f"\n1. System Design JSON"
    )

    print(
        f"   {SYSTEM_DESIGN_JSON}"
    )

    print(
        f"\n2. System Design Mermaid"
    )

    print(
        f"   {SYSTEM_DESIGN_MERMAID}"
    )

    print(
        "\nPipeline:"
    )

    print(
        """
    Business Vision
           |
           v
          BRD
           |
           v
    Jira Epics & Stories
           |
           v
    jira_epics_and_stories.json
           |
           +--------------------+
           |                    |
           v                    v
      Functional Model       ERD Model
           |                    |
           |              stories_ERD.py
           |                    |
           |                    v
           |                 erd.json
           |                    |
           +---------+----------+
                     |
                     v
             SYSTEM DESIGN LLM
                     |
                     v
            system_design.json
                     |
                     v
            system_design.mmd
                     |
                     v
          System Design PNG
        """
    )


if __name__ == "__main__":

    main()
