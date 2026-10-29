"""One HTTP call to the hosted PR analyzer. No local training or GitHub fetching."""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException


ANALYZE_URL = "https://pr-predictor-backend-gemini-api.onrender.com/analyze"
PR_URL = re.compile(r"https://github\.com/([\w-]+)/([\w.-]+)/pull/([1-9][0-9]*)/?", re.ASCII | re.I)
ERRORS = {
    401: "Analysis service rejected its API token; check PR_ANALYZER_TOKEN",
    404: "Analysis service could not find the PR or its managed token",
    422: "Analysis service rejected the request or PR URL",
    502: "Analysis service received an upstream error or invalid Gemini response",
    503: "Analysis service is not configured, over quota, or temporarily unavailable",
    504: "GitHub or Gemini request timed out",
}


def analyze_pr(pr_url: str) -> dict:
    match = PR_URL.fullmatch(pr_url.strip())
    if not match or match[2] in {".", ".."}:
        raise HTTPException(422, "Use https://github.com/owner/repo/pull/123")
    pr_url = f"https://github.com/{match[1]}/{match[2]}/pull/{match[3]}"
    token = os.getenv("PR_ANALYZER_TOKEN", "").strip()
    if not token:
        raise HTTPException(503, "Set PR_ANALYZER_TOKEN on the backend server")
    request = Request(ANALYZE_URL, method="POST",
                      data=json.dumps({"pr_url": pr_url}).encode(),
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=120) as response:
            result = json.load(response)
    except HTTPError as error:
        error.close()
        raise HTTPException(error.code if error.code in ERRORS else 502,
                            ERRORS.get(error.code, "Analysis service request failed")) from error
    except TimeoutError as error:
        raise HTTPException(504, "Analysis service request timed out") from error
    except URLError as error:
        code = 504 if isinstance(error.reason, TimeoutError) else 502
        raise HTTPException(code, "Cannot reach the analysis service") from error
    except (OSError, ValueError) as error:
        raise HTTPException(502, "Analysis service returned an unreadable response") from error

    # Check the fields used for scores/history before any credits are charged.
    try:
        analysis, features = result["analysis"], result["features"]
        if result["pr_url"].lower().rstrip("/") != pr_url.lower() or not isinstance(features, dict) or not isinstance(analysis, dict):
            raise ValueError("Invalid response")
        for key in ("merge_probability", "quality_score"):
            value = analysis[key]
            if type(value) not in (int, float) or not 0 <= value <= 100:
                raise ValueError("Invalid score")
        for key in ("quality", "summary", "merge_reasoning"):
            if not isinstance(analysis[key], str):
                raise ValueError("Invalid analysis text")
        for key in ("title", "state", "author"):
            if features.get(key) is not None and not isinstance(features[key], str):
                raise ValueError("Invalid PR metadata")
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise HTTPException(502, "Analysis service returned incomplete or invalid data") from error
    result["pr_url"] = pr_url
    return result
