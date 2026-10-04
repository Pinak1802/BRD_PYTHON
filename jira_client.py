
import asyncio
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pypdf import PdfReader


# ============================================================
# 1. CONFIGURATION
# ============================================================

MCP_PYTHON = (
    r"C:\Users\VICTUS\Downloads\fastmcp-jira"
    r"\.venv\Scripts\python.exe"
)

MCP_SERVER = (
    r"C:\Users\VICTUS\Downloads\fastmcp-jira"
    r"\server.py"
)

PDF_PATH = (
    r"C:\Users\VICTUS\Downloads\fastmcp-jira"
    r"\Business_Vision.pdf"
)

JIRA_ISSUE_KEY = "SCRUM-1"

# Read the API key from an environment variable.
API_KEY = os.getenv("LLM_API_KEY")

LLM_URL = os.getenv(
    "LLM_URL",
    "https://api.apinex.bond/v1/chat/completions"
)

MODEL = "free/gpt-6-luna"


# ============================================================
# 2. EXTRACT TEXT FROM MCP TOOL RESULTS
# ============================================================

def extract_tool_text(result):

    if result is None:
        return ""

    if getattr(result, "is_error", False):
        raise RuntimeError(
            f"MCP tool failed: {result}"
        )

    content = getattr(result, "content", None)

    if content is None:
        return str(result)

    texts = []

    for item in content:
        if hasattr(item, "text"):
            texts.append(item.text)

    return "\n".join(texts)


# ============================================================
# 3. EXTRACT TEXT FROM BUSINESS VISION PDF
# ============================================================

def extract_pdf_text(pdf_path):

    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Business Vision PDF not found: {path}"
        )

    reader = PdfReader(str(path))

    pages = []

    for page in reader.pages:
        pages.append(page.extract_text() or "")

    return "\n".join(pages).strip()


# ============================================================
# 4. CALL LLM TO GENERATE THE BRD
# ============================================================

def generate_brd(prompt, business_vision):

    if not API_KEY:
        raise RuntimeError(
            "Set the LLM_API_KEY environment variable first."
        )

    # Combine the MCP prompt and PDF text.
    user_message = (
        prompt
        + "\n\nBusiness Vision:\n"
        + business_vision
    )

    # Create the same OpenAI-compatible request
    # structure used in the Java application.
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": user_message
            }
        ]
    }

    json_data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=LLM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
            "User-Agent": "BRD-Python-Client/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request) as response:
            status_code = response.status
            response_body = response.read().decode("utf-8")


    except urllib.error.HTTPError as error:
        error_body = error.read().decode(
            "utf-8", errors="replace"
        )

        print("LLM HTTP status:", error.code)
        print("LLM response headers:", error.headers)
        print("LLM response body:", error_body)

        raise RuntimeError(
            f"LLM API failed: HTTP {error.code}\n{error_body}"
        ) from error

    print(f"\nLLM HTTP STATUS: {status_code}")

    # Parse the OpenAI-compatible response.
    root = json.loads(response_body)

    brd = (
        root.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )

    if not isinstance(brd, str) or not brd.strip():
        raise RuntimeError(
            f"LLM returned an empty BRD. Response: {response_body}"
        )

    return brd


# ============================================================
# 5. MAIN WORKFLOW: MCP -> PDF -> PROMPT -> LLM -> BRD
# ============================================================

async def main():

    print("Starting Python MCP client...")

    # Launch the local FastMCP server as a subprocess.



    transport = StdioTransport(
        command=MCP_PYTHON,
        args=[MCP_SERVER],
        env={
            **os.environ,
            "JIRA_BASE_URL": os.environ["JIRA_BASE_URL"],
            "JIRA_EMAIL": os.environ["JIRA_EMAIL"],
            "JIRA_API_TOKEN": os.environ["JIRA_API_TOKEN"],
        },
    )

    async with Client(transport) as client:

        print("Connected to FastMCP server!")

        # ----------------------------------------------------
        # STEP 1: DOWNLOAD BUSINESS VISION FROM JIRA
        # ----------------------------------------------------

        print("\nDownloading Business Vision from Jira...")

        vision_result = await client.call_tool(
            "download_business_vision",
            {"issue_key": JIRA_ISSUE_KEY}
        )

        vision_tool_text = extract_tool_text(vision_result)

        print("Business Vision tool response:")
        print(vision_tool_text)

        if (
            "Failed" in vision_tool_text
            or "not found" in vision_tool_text.lower()
        ):
            raise RuntimeError(
                "Could not download Business Vision from Jira."
            )

        # ----------------------------------------------------
        # STEP 2: RETRIEVE THE BRD PROMPT FROM FASTMCP
        # ----------------------------------------------------

        print("\nRetrieving BRD prompt...")

        prompt_result = await client.call_tool(
            "get_brd_prompt",
            {}
        )

        brd_prompt = extract_tool_text(prompt_result)

        if not brd_prompt.strip():
            raise RuntimeError(
                "FastMCP returned an empty BRD prompt."
            )

        print("BRD prompt retrieved successfully.")

        # ----------------------------------------------------
        # STEP 3: EXTRACT TEXT FROM THE DOWNLOADED PDF
        # ----------------------------------------------------

        print("\nExtracting Business Vision PDF text...")

        business_vision = extract_pdf_text(PDF_PATH)

        if not business_vision:
            raise RuntimeError(
                "Business Vision PDF contains no readable text."
            )

        print("\nBusiness Vision text:")
        print(business_vision)

        # ----------------------------------------------------
        # STEP 4: SEND PROMPT + BUSINESS VISION TO THE LLM
        # ----------------------------------------------------

        print("\nGenerating Business Requirements Document...")

        brd = generate_brd(
            brd_prompt,
            business_vision
        )

        # ----------------------------------------------------
        # STEP 5: DISPLAY AND SAVE THE BRD
        # ----------------------------------------------------

        print("\n" + "=" * 60)
        print("GENERATED BUSINESS REQUIREMENTS DOCUMENT")
        print("=" * 60)
        print(brd)

        output_path = Path(__file__).resolve().parent / "BRD.txt"
        output_path.write_text(brd, encoding="utf-8")

        print(f"\nBRD saved to: {output_path}")
        print("BRD generation completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())