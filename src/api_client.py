"""Shopmetrics API v2 client: OAuth2 auth, Query API, and Command API.

Implements the real Shopmetrics endpoints described in SPECIFICATION.md
section 2 (sourced from _KNOWLEDGEBASE/023-APIs/). Uses only the standard
library so the pipeline has zero third-party dependencies.

Used when EXTRACTION_MODE=api and/or COMMAND_MODE=live. In the default
file/mock configuration this module's network functions are not called.
"""

import json
import time
import urllib.error
import urllib.request

import config

_token_cache = {"access_token": None, "expires_at": 0}

# Shopmetrics sits behind a WAF that blocks the default Python urllib
# User-Agent (HTTP 403 / Cloudflare error 1010). A normal browser-style
# User-Agent is required for requests to be accepted.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class ShopmetricsAPIError(Exception):
    pass


def _post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", _USER_AGENT)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        raise ShopmetricsAPIError(f"HTTP {e.code} calling {url}: {e.read().decode('utf-8', 'ignore')}") from e
    except urllib.error.URLError as e:
        raise ShopmetricsAPIError(f"Network error calling {url}: {e.reason}") from e


def _post_form(url: str, fields: dict, headers: dict | None = None) -> dict:
    data = _urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", _USER_AGENT)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ShopmetricsAPIError(f"HTTP {e.code} calling {url}: {e.read().decode('utf-8', 'ignore')}") from e
    except urllib.error.URLError as e:
        raise ShopmetricsAPIError(f"Network error calling {url}: {e.reason}") from e


def _urlencode(fields: dict) -> str:
    from urllib.parse import urlencode

    return urlencode(fields)


def get_access_token() -> str:
    """Client Credentials Grant Flow (APIAUT). Caches the token until it expires."""
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    if not config.SHOPMETRICS_CLIENT_ID or not config.SHOPMETRICS_CLIENT_SECRET:
        raise ShopmetricsAPIError(
            "SHOPMETRICS_CLIENT_ID / SHOPMETRICS_CLIENT_SECRET are not set. "
            "Required when EXTRACTION_MODE=api or COMMAND_MODE=live."
        )

    response = _post_form(
        config.TOKEN_ENDPOINT,
        {
            "client_id": config.SHOPMETRICS_CLIENT_ID,
            "client_secret": config.SHOPMETRICS_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
    )
    token = response["access_token"]
    expires_in = response.get("expires_in", 1800)
    _token_cache["access_token"] = token
    _token_cache["expires_at"] = now + int(expires_in) - 30  # refresh a bit early
    return token


def _execute_dataset(dataset_name: str, parameters: list[dict]) -> list[dict]:
    """Calls POST /api/v2/execute for a given dataset (APIQRY, APICA).

    Per the KB examples, the request body is form-encoded with a single
    "post" field whose value is the JSON string describing the dataset call
    -- not a JSON request body.
    """
    token = get_access_token()
    post_payload = json.dumps(
        {"action": "exec", "dataset": {"datasetname": dataset_name}, "parameters": parameters}
    )
    response = _post_form(
        config.QUERY_ENDPOINT,
        {"post": post_payload},
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        return response["dataset"]["data"][0]
    except (KeyError, IndexError, TypeError):
        return []


def list_client_or_form_ids() -> list[dict]:
    """Discovers the ClientOrFormIDs values this API user can query (APICAP)."""
    return _execute_dataset(
        "/Apps/SM/APIv2/Query/ClientAnalytics/Parameter_ClientOrFormIDs",
        [
            {"name": "SecurityObjectUserID", "value": None},
            {"name": "LanguageLocale", "value": None},
            {"name": "ClientOrFormIDs", "value": None},
            {"name": "SurveyTypeIDs", "value": None},
            {"name": "ExcludeClientOrFormIDs", "value": None},
            {"name": "IsIncludeClientGroups", "value": None},
            {"name": "IsIncludeClients", "value": None},
            {"name": "IsIncludeSurveyFamilies", "value": None},
            {"name": "IsIncludeSurveyForms", "value": None},
        ],
    )


# Only the fields this project actually stores and uses (surveys table
# columns, dashboard, view, delete-surveys filters) -- see load.py's
# _survey_values()/_INSERT_COLUMNS for the exact set this maps to. The
# Client Analytics dataset offers many more fields (full location address,
# raw points, custom properties, export/RFA/audit status flags -- see
# SPECIFICATION.md section 2's history for the full list and why it was
# tried and reverted); deliberately not requesting them keeps the query
# lean and the schema free of columns nothing ever reads.
_SURVEY_LIST_FIELDS = (
    "[InstanceID][Title][Loc ID][Location Name][Date][ScorePctXX.XX]"
    "[SurveyStatusName][AttachmentsCount][Login][Shopper Name][WorkflowStepID][Campaign]"
    "[IsSurveyInstanceViewedBySecurityUser]"
)


def list_surveys(client_or_form_id: str, limit: int, unopened_only: bool = False) -> list[dict]:
    """Lists survey instances for a given ClientOrFormIDs value (APICA)."""
    where_clause = "[WHERE:IsSurveyInstanceViewedBySecurityUser|0]" if unopened_only else ""
    query_spec = f"{_SURVEY_LIST_FIELDS}{where_clause}[ORDERBY:Date|DESC]"
    rows = _execute_dataset(
        config.CLIENT_ANALYTICS_DATASET,
        [
            {"name": "QuerySpecification", "value": query_spec},
            {"name": "ClientOrFormIDs", "value": client_or_form_id},
        ],
    )
    return rows[:limit]


def get_survey_responses(survey_ids: list[str]) -> dict[str, list[dict]]:
    """Fetches [QuestionID][ProtoAnswerText][Question Comment] rows for the
    given survey instance IDs, grouped by survey_id (APICAUC)."""
    if not survey_ids:
        return {}
    rows = _execute_dataset(
        config.CLIENT_ANALYTICS_DATASET,
        [
            {"name": "QuerySpecification", "value": "[InstanceID][QuestionID][ProtoAnswerText][Question Comment]"},
            {"name": "SurveyInstanceIDs", "value": ",".join(survey_ids)},
        ],
    )
    responses_by_instance: dict[str, list[dict]] = {}
    for r in rows:
        instance_id = str(r["InstanceID"])
        responses_by_instance.setdefault(instance_id, []).append(
            {
                "question_id": str(r.get("QuestionID", "")),
                "answer_text": r.get("ProtoAnswerText"),
                "comment": r.get("Question Comment"),
            }
        )
    return responses_by_instance


def query_new_surveys() -> list[dict]:
    """Fetches survey instances not yet opened by the client user, plus their
    responses, and returns them normalized to the same shape as file-mode
    sample data. See SPECIFICATION.md section 6.1.
    """
    rows = list_surveys(
        config.SHOPMETRICS_CLIENT_OR_FORM_IDS,
        config.SHOPMETRICS_MAX_RECORDS_PER_RUN,
        unopened_only=True,
    )
    if not rows:
        return []

    instance_ids = [str(row["InstanceID"]) for row in rows]
    responses_by_instance = get_survey_responses(instance_ids)

    records = []
    for row in rows:
        instance_id = str(row["InstanceID"])
        records.append(
            {
                "survey_id": instance_id,
                "client_or_form_id": config.SHOPMETRICS_CLIENT_OR_FORM_IDS,
                "survey_title": row.get("Title"),
                "location_store_id": str(row.get("Loc ID", "")) or None,
                "location_name": row.get("Location Name"),
                "submitted_at": row.get("Date"),
                "score": row.get("ScorePctXX.XX"),
                "responses": responses_by_instance.get(instance_id, []),
                "campaign": row.get("Campaign"),
                "survey_status": row.get("SurveyStatusName"),
                "attachments_count": row.get("AttachmentsCount"),
                "fieldworker_login": row.get("Login"),
                "fieldworker_name": row.get("Shopper Name"),
                "workflow_step_id": row.get("WorkflowStepID"),
            }
        )
    return records


def mark_survey_opened_live(survey_id: str) -> str:
    """Real "mark opened" call (SIPB): flips IsSurveyInstanceViewedBySecurityUser
    to 1 for this survey instance via the BulkProcessing_SetReadStatus command
    dataset -- called through the same /api/v2/execute transport the Query API
    uses (command-as-dataset convention; see SPECIFICATION.md section 2), not
    the dedicated REST /api/v2/command/<Name> path. Returns the RequestUUID for
    later status lookup via CommandStatusCheck.

    This is Shopmetrics' own documented mechanism for exactly this ETL
    scenario (SIPB is their Power BI ETL integration guide) -- tested live
    and currently fails with HTTP 500 (likely deprecated on newer platform
    versions), see SPECIFICATION.md section 10.3.
    """
    token = get_access_token()
    post_payload = json.dumps(
        {
            "action": "exec",
            "dataset": {"datasetname": "/Apps/SM/APIv2/Command/SurveyInstances/BulkProcessing_SetReadStatus"},
            "parameters": [
                {"name": "SurveyInstancesIDsCSV", "value": str(survey_id)},
                {"name": "ReadStatus", "value": "1"},
            ],
        }
    )
    response = _post_form(
        config.QUERY_ENDPOINT,
        {"post": post_payload},
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        request_uuid = response["dataset"]["data"]["RequestUUID"]
    except (KeyError, TypeError):
        raise ShopmetricsAPIError(f"BulkProcessing_SetReadStatus did not return a RequestUUID: {response}")
    return request_uuid


def grant_client_access_live(survey_id: str) -> str:
    """Real Command API call (APIQCRC): sets ClientAccessStatus to 'OK for
    Client Access'. A real, valid command -- but answers a different question
    ("grant Client Access status") than "mark opened". Kept available but not
    used by mark_survey_opened(); see SPECIFICATION.md section 10.2 for why
    this was originally (incorrectly) used as the "mark opened" mechanism.
    """
    token = get_access_token()
    import_data = f"SurveyInstanceID\tClientAccessStatus\n{survey_id}\tOK for Client Access"
    response = _post_json(
        config.COMMAND_QC_ENDPOINT,
        {"ImportData": import_data, "ImportNote": config.QC_IMPORT_NOTE},
        headers={"Authorization": f"Bearer {token}"},
    )
    request_id = response.get("RequestID") or response.get("requestId") or response.get("id")
    if not request_id:
        raise ShopmetricsAPIError(f"Command API did not return a Request ID: {response}")
    return request_id


def mark_survey_opened_mock(survey_id: str) -> str:
    """Simulated Command API call: always succeeds, no network access."""
    return f"MOCK-REQUEST-{survey_id}"


def mark_survey_opened(survey_id: str) -> str:
    if config.COMMAND_MODE == "live":
        return mark_survey_opened_live(survey_id)
    return mark_survey_opened_mock(survey_id)
