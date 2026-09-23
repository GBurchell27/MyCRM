"""Draft task emails with AI and open them as Outlook drafts for the user to send.

Nothing here ever sends an email. AI drafting returns text for the user to
review; opening in Outlook uses COM automation to pop a draft window (Outlook
resolves recipient names against contacts/the company address book). If COM is
unavailable (e.g. "new Outlook"), we fall back to a mailto: draft.
"""

import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import webbrowser

from ai_client import chat_completion
from ai_summarizer import _client
from config.ai_models import EMAIL, chat_completion_kwargs

EMAIL_SYSTEM = """You draft short professional work emails on behalf of the user.

Return ONLY valid JSON with this shape:
{
  "to_name": "Recipient's name if one can be inferred from the input, else \\"\\"",
  "subject": "Concise, specific subject line",
  "body": "The full email body as plain text"
}

Rules:
- Write in first person as the sender. Friendly, professional, concise.
- Get to the point in the first sentence or two.
- Greet the recipient by first name when a name is given.
- Do not invent facts, dates, or commitments not supported by the input.
- Do not add a signature block - the user's email client appends one.
"""


def build_email_context(title, notes=""):
    parts = [f"Task: {(title or '').strip()}"]
    if notes and notes.strip():
        parts.append("Task notes:\n" + notes.strip())
    return "\n\n".join(parts)


def draft_email(context, recipient=""):
    """
    Ask the AI to draft an email from the task/context text.
    Returns dict: to_name, subject, body.
    Raises RuntimeError with a user-facing message on failure.
    """
    if not context.strip():
        raise RuntimeError("Nothing to draft from - describe what the email should say.")
    client = _client()
    parts = [context.strip()]
    if recipient.strip():
        parts.append("Recipient: " + recipient.strip())

    response = chat_completion(
        client,
        messages=[
            {"role": "system", "content": EMAIL_SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)},
        ],
        response_format={"type": "json_object"},
        **chat_completion_kwargs(EMAIL),
    )
    content = response.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI returned invalid JSON. Try again.") from exc

    return {
        "to_name": str(data.get("to_name") or "").strip(),
        "subject": str(data.get("subject") or "").strip(),
        "body": str(data.get("body") or "").strip(),
    }


# Reads the draft parts from temp files so no shell escaping is ever needed.
# Recipients.ResolveAll makes Outlook match a plain name ("Jane Doe")
# against contacts and the company address book before the window opens.
_OUTLOOK_SCRIPT = """$to = (Get-Content -Raw -LiteralPath $args[0]).Trim()
$subject = (Get-Content -Raw -LiteralPath $args[1]).Trim()
$body = Get-Content -Raw -LiteralPath $args[2]
$outlook = New-Object -ComObject Outlook.Application
$mail = $outlook.CreateItem(0)
if ($to) { $mail.To = $to }
$mail.Subject = $subject
$mail.Body = $body
$null = $mail.Recipients.ResolveAll()
$mail.Display()
"""


def open_outlook_draft(to, subject, body):
    """
    Open a new Outlook draft window with the fields prefilled. Never sends.
    Returns "outlook" if the COM draft opened, "mailto" if it fell back.
    Raises RuntimeError if neither route worked.
    """
    work_dir = tempfile.mkdtemp(prefix="email_draft_")
    try:
        paths = []
        for name, text in (("to", to), ("subject", subject), ("body", body)):
            path = os.path.join(work_dir, name + ".txt")
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write(text or "")
            paths.append(path)
        script_file = os.path.join(work_dir, "open_draft.ps1")
        with open(script_file, "w", encoding="utf-8-sig") as f:
            f.write(_OUTLOOK_SCRIPT)

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script_file,
            ]
            + paths,
            capture_output=True,
            timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            return "outlook"
    except (OSError, subprocess.TimeoutExpired):
        pass
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return _open_mailto_draft(to, subject, body)


def _open_mailto_draft(to, subject, body):
    query = urllib.parse.urlencode(
        {"subject": subject or "", "body": body or ""},
        quote_via=urllib.parse.quote,
    )
    url = "mailto:" + urllib.parse.quote(to or "") + "?" + query
    if webbrowser.open(url):
        return "mailto"
    raise RuntimeError(
        "Could not open Outlook (COM automation failed) and the mailto: "
        "fallback did not open either. Check that a mail client is installed."
    )
