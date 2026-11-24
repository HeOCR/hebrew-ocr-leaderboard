"""Shared aggregate format for the Space and bilingual site builder."""

from datetime import date
import json
from math import isfinite
import re
from pathlib import Path

SCHEMA = "heocr.leaderboard.results.v1"
DATASET = "HeOCR/p-mod-open-v0"
RESULTS_REPO = "HeOCR/hebrew-ocr-leaderboard-results"
MANIFEST = "f173417a49f960f8bdd2bf9950a9e676d2070aeb6d6a6a3b0066887af6a11190"
CATEGORIES = {
    "C1": ("Modern unpointed print", "דפוס מודרני ללא ניקוד"),
    "C2": ("Historical unpointed print", "דפוס היסטורי ללא ניקוד"),
    "C3": ("Modern pointed print", "דפוס מודרני מנוקד"),
    "C4": ("Historical pointed print", "דפוס היסטורי מנוקד"),
    "C5": ("Modern handwriting", "כתב יד מודרני"),
    "C6": ("Historical handwriting", "כתב יד היסטורי"),
}
STRATA = {
    "pooled": ("Pooled page CER", "שגיאת תווים מצרפית"),
    "archive": ("Archive", "ארכיון"),
    "issuer-render": ("Issuer render", "תצוגת המוציא לאור"),
    "issuer-scan": ("Issuer scan", "סריקת המוציא לאור"),
    "scanner": ("Office scanner", "סורק משרדי"),
    "phone-a": ("Phone A", "טלפון א׳"),
    "phone-b": ("Phone B", "טלפון ב׳"),
}
VIEWS = {
    "filtered": ("Common filtered positions", "מיקומים משותפים לאחר סינון"),
    "all": ("All reference positions", "כל המיקומים בטקסט הייחוס"),
}
READER_TYPES = {
    "open weights": "משקולות פתוחות", "closed weights": "משקולות סגורות",
    "API": "API", "commercial API": "API מסחרי",
}
BIAS_NOTICE = "same model family took part in building v0 references (biased comparator)"
ARTWORK_MASK_NOTICE = '56 carriers match the original scored pixels. Nine artwork-masked carriers are a separate diagnostic.'
DIAGNOSTIC_NOTICES = {
    "google-vision-document-text-v0": ARTWORK_MASK_NOTICE,
    "google-document-ai-ocr-v21-v0": ARTWORK_MASK_NOTICE,
    "claude-haiku-5-5-v0": ARTWORK_MASK_NOTICE,
    "claude-haiku-4-5-v0": (
        ARTWORK_MASK_NOTICE
        + " 64/65 Haiku 4.5 replies were Hebrew-dominant (median 100% Hebrew letters), 1 Latin-dominant."
        " 11 hit the output cap."
    ),
}
SHA = re.compile(r"[a-f0-9]{64}")
ROW_ID = re.compile(r"[a-z0-9-]{1,64}")
BASELINES = {"rivok-full", "rivok-lite", "tessdata-best", "tessdata-fast", "paddle"}


EFFICIENCY_PLATFORMS = {
    "m4-cpu": ("Apple M4 CPU", "מעבד Apple M4"),
    "github-ubuntu-cpu": ("GitHub Ubuntu CPU", "מעבד GitHub Ubuntu"),
    "registered-api": ("Registered API runs", "הרצות API רשומות"),
}
EFFICIENCY_EXECUTIONS = {
    "native-tesseract": ("measured", "Native Tesseract · measured", "נמדד · Tesseract מקומי"),
    "onnx-cpu": ("measured-cpu-variant", "ONNX CPU · measured variant", "נמדד · גרסת ONNX למעבד"),
    "vertex-global-https": ("list-price-only", "Vertex global · list prices only", "Vertex גלובלי · מחירי מחירון בלבד"),
}
MEASUREMENTS = (
    "pages", "repetitions", "pages_per_minute", "peak_rss_mib",
    "marginal_usd_per_1000", "runner_hours_per_1000", "runner_usd_per_1000",
)
TOKEN_RATES = ("api_input_usd_per_million", "api_output_usd_per_million")
API_TIMING_LABEL = "from registered run; network-bound, not comparable to local CPU"
API_EXECUTIONS = {
    "vertex-global-https": ("Vertex global", "Vertex גלובלי"),
    "vision-document-text-detection": ("Vision Document Text Detection", "Vision Document Text Detection"),
    "document-ai-enterprise-ocr": ("Document AI Enterprise OCR", "Document AI Enterprise OCR"),
    "anthropic-message-batch": ("Anthropic Message Batches", "Anthropic Message Batches"),
}
API_STATUSES = {
    (False, False): ("list-price-only", "list prices only", "מחירי מחירון בלבד"),
    (True, False): ("registered-cost-only", "list cost from usage", "עלות מחירון לפי שימוש מדווח"),
    (False, True): ("registered-timing-only", "recorded timing", "תזמון מדווח"),
    (True, True): ("registered", "list cost and timing", "עלות מחירון ותזמון"),
}
API_TIMING_NUMBERS = ("api_pages_per_minute", "api_mean_request_latency_seconds", "api_timed_pages")
API_NUMBERS = ("api_usd_per_1000_units", *API_TIMING_NUMBERS)
API_TEXT = ("api_registration", "api_timing_scope", "api_timing_label")


def validate_registered_api(row):
    has_timing = row["api_timing_scope"] is not None
    has_cost = row["marginal_usd_per_1000"] is not None
    if (row["execution"] not in API_EXECUTIONS
            or row["status"] != API_STATUSES[has_cost, has_timing][0]
            or row["api_timing_label"] != API_TIMING_LABEL
            or not isinstance(row["api_registration"], str)
            or not re.fullmatch(r"#[1-9][0-9]*", row["api_registration"])
            or any(row[name] is not None for name in ("pages_per_minute", "runner_hours_per_1000", "runner_usd_per_1000"))):
        raise ValueError("Invalid registered API efficiency scope")
    if has_timing:
        if (not text(row["api_timing_scope"], 96) or type(row["api_timed_pages"]) is not int
                or not 0 < row["api_timed_pages"] <= row["pages"]
                or not any(row[name] is not None for name in API_TIMING_NUMBERS[:2])):
            raise ValueError("Invalid registered API timing")
    elif any(row[name] is not None for name in API_TIMING_NUMBERS):
        raise ValueError("Registered API timing requires its recorded scope")



def validate_efficiency(table, reader_ids):
    if (not isinstance(table, dict) or table.keys() != {"source_commit", "source_sha256", "rows"}
            or not isinstance(table["source_commit"], str) or not re.fullmatch(r"[a-f0-9]{40}", table["source_commit"])
            or not isinstance(table["source_sha256"], str) or not SHA.fullmatch(table["source_sha256"])
            or not isinstance(table["rows"], list)):
        raise ValueError("Invalid efficiency source")
    pairs = set()
    fields = {"reader_id", "platform", "execution", "status", *MEASUREMENTS, *TOKEN_RATES}
    for row in table["rows"]:
        if not isinstance(row, dict) or not isinstance(row.get("platform"), str):
            raise ValueError("Invalid efficiency row fields")
        registered = row["platform"] == "registered-api"
        if row.keys() != (fields | {*API_NUMBERS, *API_TEXT} if registered else fields):
            raise ValueError("Invalid efficiency row fields")
        key = row["reader_id"], row["platform"]
        if (not all(isinstance(row[name], str) for name in ("reader_id", "execution", "status"))
                or key[0] not in reader_ids or key[1] not in EFFICIENCY_PLATFORMS or key in pairs):
            raise ValueError("Invalid or repeated efficiency join")
        pairs.add(key)
        numbers = (*MEASUREMENTS, *TOKEN_RATES, *API_NUMBERS) if registered else (*MEASUREMENTS, *TOKEN_RATES)
        if any(v is not None and (type(v) not in (float, int) or not isfinite(v) or v < 0)
               for v in (row[name] for name in numbers)):
            raise ValueError("Invalid efficiency value")
        if registered:
            if any(type(row[name]) is not int or row[name] < 1 for name in ("pages", "repetitions")):
                raise ValueError("Missing registered API run coverage")
            validate_registered_api(row)
            continue
        execution = EFFICIENCY_EXECUTIONS.get(row["execution"])
        if execution is None or row["status"] != execution[0]:
            raise ValueError("Invalid local efficiency execution")
        if row["status"] == "list-price-only":
            if any(row[name] is not None for name in MEASUREMENTS) or any(row[name] is None for name in TOKEN_RATES):
                raise ValueError("A list-price-only row cannot contain measurements")
        elif (any(type(row[name]) is not int or row[name] < 1 for name in ("pages", "repetitions"))
              or any(row[name] is None for name in MEASUREMENTS[:-1])
              or any(row[name] is not None for name in TOKEN_RATES)):
            raise ValueError("Incomplete local efficiency measurements")


def text(value, length):
    return isinstance(value, str) and 0 < len(value) <= length and value == value.strip() and value.isprintable()


def valid_metrics(groups):
    if not isinstance(groups, dict) or groups.keys() != STRATA.keys():
        return False
    for item in groups.values():
        if not isinstance(item, dict) or item.keys() != {"edits", "chars"}:
            return False
        if any(type(x) is not int or x < 0 for x in item.values()) or (item["chars"] == 0 and item["edits"] != 0):
            return False
    return groups["pooled"]["chars"] > 0 and all(
        groups["pooled"][key] == sum(group[key] for name, group in groups.items() if name != "pooled")
        for key in ("edits", "chars")
    )


def valid_views(views):
    return isinstance(views, dict) and views.keys() == VIEWS.keys() and all(
        valid_metrics(groups) for groups in views.values()
    )


def validate(data):
    fields = {"schema", "benchmark", "rows"}
    if (not isinstance(data, dict) or data.keys() not in (fields, fields | {"efficiency"})
            or data["schema"] != SCHEMA):
        raise ValueError("Invalid leaderboard schema")
    if data["benchmark"] != {"dataset": DATASET, "manifest_sha256": MANIFEST, "pages": 31, "carriers": 65}:
        raise ValueError("Invalid benchmark scope")
    if not isinstance(data["rows"], list):
        raise ValueError("Invalid leaderboard rows")
    ids = set()
    for row in data["rows"]:
        fields = {"id", "category", "reader", "version", "type", "licence", "date", "scorer_version",
                  "verified", "submission_sha256", "views"}
        if not isinstance(row, dict) or row.keys() not in (fields, fields | {"diagnostic"}):
            raise ValueError("Invalid row fields")
        if not isinstance(row["id"], str) or not ROW_ID.fullmatch(row["id"]) or row["id"] in ids:
            raise ValueError("Invalid or repeated reader row")
        ids.add(row["id"])
        if (row["category"] != "C1" or row["type"] not in READER_TYPES or type(row["verified"]) is not bool
                or re.match(r"^heocr\b", str(row["reader"]), re.IGNORECASE)):
            raise ValueError("Invalid row classification")
        if not all(text(row[key], limit) for key, limit in
                   (("reader", 80), ("version", 60), ("licence", 80), ("scorer_version", 100))):
            raise ValueError("Invalid reader display fields")
        if not isinstance(row["date"], str) or date.fromisoformat(row["date"]).isoformat() != row["date"]:
            raise ValueError("Invalid result date")
        key = row["submission_sha256"]
        if key is not None and (not isinstance(key, str) or not SHA.fullmatch(key) or row["id"] != key):
            raise ValueError("Invalid submission pin")
        if key is None and not row["verified"]:
            raise ValueError("Unverified rows require a submission pin")
        if not valid_views(row["views"]):
            raise ValueError("Invalid score breakdown")
        if "diagnostic" in row:
            diagnostic = row["diagnostic"]
            if (not isinstance(diagnostic, dict)
                    or diagnostic.keys() != {"notice", "paired_carriers", "masked_carriers", "masked_views"}
                    or diagnostic["notice"] != DIAGNOSTIC_NOTICES.get(row["id"], BIAS_NOTICE)
                    or (diagnostic["paired_carriers"], diagnostic["masked_carriers"]) != (56, 9)
                    or not valid_views(diagnostic["masked_views"])
                    or row["type"] != "commercial API" or not row["verified"] or key is not None):
                raise ValueError("Invalid diagnostic breakdown")
    if not BASELINES <= {row["id"] for row in data["rows"] if row["verified"] and row["submission_sha256"] is None}:
        raise ValueError("Required external baselines are missing")
    if "efficiency" in data:
        validate_efficiency(data["efficiency"], ids)
    return data


def read_results(path: Path):
    return validate(json.loads(path.read_bytes()))


def cer(metric):
    return metric["edits"] / metric["chars"] if metric["chars"] else None


def percentage(metric):
    value = cer(metric)
    return "—" if value is None else f"{value:.2%}"


def ranked(data, view):
    return sorted((row for row in data["rows"] if "diagnostic" not in row), key=lambda row: (cer(row["views"][view]["pooled"]), row["reader"].casefold(), row["id"]))
