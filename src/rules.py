from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from rapidfuzz import fuzz

from .normalize import adjacent_line_windows, canonical_abv, canonical_volume, compact_for_match, normalize_text

STANDARD_GOV_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate "
    "machinery, and may cause health problems."
)

COUNTRY_SYNONYMS = {
    "scotland": ["scotland", "product of scotland", "scotch"],
    "ireland": ["ireland", "product of ireland", "irish"],
    "mexico": ["mexico", "product of mexico"],
    "france": ["france", "product of france"],
    "canada": ["canada", "product of canada"],
    "italy": ["italy", "product of italy"],
    "spain": ["spain", "product of spain"],
    "japan": ["japan", "product of japan"],
}

@dataclass
class FieldResult:
    field: str
    expected: str
    status: str
    score: Optional[float]
    message: str
    evidence: str
    issue_category: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


def _nearest_snippet(needle: str, haystack: str, window: int = 95) -> str:
    normalized_haystack = normalize_text(haystack).replace("\n", " ")
    words = [w for w in re.split(r"\W+", needle) if len(w) >= 4]
    lower = normalized_haystack.lower()
    for word in words:
        pos = lower.find(word.lower())
        if pos >= 0:
            return normalized_haystack[max(0, pos-window): min(len(normalized_haystack), pos+len(word)+window)]
    return normalized_haystack[:220]


def best_fuzzy_score(expected: str, ocr_text: str) -> tuple[float, str]:
    expected_clean = compact_for_match(expected)
    candidates = adjacent_line_windows(ocr_text, max_window=3)
    candidates.append(compact_for_match(ocr_text))
    best_score = 0.0
    best_candidate = ""
    for cand in candidates:
        scores = [
            fuzz.ratio(expected_clean, cand),
            fuzz.partial_ratio(expected_clean, cand),
            fuzz.token_sort_ratio(expected_clean, cand),
            fuzz.token_set_ratio(expected_clean, cand),
        ]
        score = max(scores)
        if score > best_score:
            best_score = float(score)
            best_candidate = cand
    return best_score, best_candidate


def fuzzy_field_check(field: str, expected: str, ocr_text: str, threshold: int = 88, review_threshold: int = 70) -> FieldResult:
    if not expected:
        return FieldResult(field, expected, "Not checked", None, "No expected value was provided.", "")
    if not ocr_text.strip():
        return FieldResult(field, expected, "Fail", 0, "No OCR text was extracted.", "", field)
    score, candidate = best_fuzzy_score(expected, ocr_text)
    if score >= threshold:
        status = "Pass"
        message = "Expected value appears on the label."
    elif score >= review_threshold:
        status = "Review"
        message = "Possible match found; human review recommended."
    else:
        status = "Fail"
        message = "Expected value was not found with sufficient similarity."
    return FieldResult(field, expected, status, round(score, 1), message, candidate or _nearest_snippet(expected, ocr_text), field)


def alcohol_content_check(expected: str, ocr_text: str) -> FieldResult:
    if not expected:
        return FieldResult("Alcohol content", expected, "Not checked", None, "No expected value was provided.", "")
    expected_clean = canonical_abv(expected)
    ocr_clean = canonical_abv(ocr_text)
    expected_percent = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", expected_clean)
    expected_proof = re.search(r"(\d{1,3}(?:\.\d+)?)\s*proof", expected_clean)
    label_percents = re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", ocr_clean)
    label_proofs = re.findall(r"(\d{1,3}(?:\.\d+)?)\s*proof", ocr_clean)
    checks = []
    evidence = []
    if expected_percent:
        expected_pct = float(expected_percent.group(1))
        checks.append(any(abs(float(p) - expected_pct) < 0.05 for p in label_percents))
        evidence.append(f"Detected % values: {label_percents or 'none'}")
    if expected_proof:
        expected_pf = float(expected_proof.group(1))
        checks.append(any(abs(float(p) - expected_pf) < 0.05 for p in label_proofs))
        evidence.append(f"Detected proof values: {label_proofs or 'none'}")
    if not checks:
        return fuzzy_field_check("Alcohol content", expected, ocr_text, threshold=86, review_threshold=72)
    if all(checks):
        return FieldResult("Alcohol content", expected, "Pass", 100, "Alcohol content values match.", "; ".join(evidence), "Alcohol content")
    if any(checks):
        return FieldResult("Alcohol content", expected, "Review", 75, "Some alcohol content values matched, but not all.", "; ".join(evidence), "Alcohol content")
    return FieldResult("Alcohol content", expected, "Fail", 0, "Expected alcohol content was not found.", "; ".join(evidence), "Alcohol content")


def net_contents_check(expected: str, ocr_text: str) -> FieldResult:
    if not expected:
        return FieldResult("Net contents", expected, "Not checked", None, "No expected value was provided.", "")
    expected_clean = canonical_volume(expected)
    ocr_clean = canonical_volume(ocr_text)
    volume_match = re.search(r"(\d+(?:\.\d+)?)\s*(ml|l)\b", expected_clean)
    label_volumes = re.findall(r"(\d+(?:\.\d+)?)\s*(ml|l)\b", ocr_clean)
    if volume_match:
        expected_value = float(volume_match.group(1))
        expected_unit = volume_match.group(2)
        matched = any(float(v) == expected_value and unit == expected_unit for v, unit in label_volumes)
        evidence = f"Detected volume values: {[' '.join(v) for v in label_volumes] or 'none'}"
        if matched:
            return FieldResult("Net contents", expected, "Pass", 100, "Net contents match.", evidence, "Net contents")
        return FieldResult("Net contents", expected, "Fail", 0, "Expected net contents were not found.", evidence, "Net contents")
    return fuzzy_field_check("Net contents", expected, ocr_text, threshold=86, review_threshold=72)


def country_of_origin_check(expected: str, ocr_text: str) -> FieldResult:
    if not expected:
        return FieldResult("Country of origin", expected, "Not checked", None, "No expected country of origin was provided.", "")
    compact = compact_for_match(ocr_text)
    exp = compact_for_match(expected)
    candidates = COUNTRY_SYNONYMS.get(exp, [exp, f"product of {exp}"])
    found = [c for c in candidates if compact_for_match(c) in compact]
    if found:
        return FieldResult("Country of origin", expected, "Pass", 100, "Expected country of origin appears on the label.", ", ".join(found), "Country of origin")
    score, candidate = best_fuzzy_score(expected, ocr_text)
    if score >= 75:
        return FieldResult("Country of origin", expected, "Review", round(score,1), "Possible country match found; review recommended.", candidate, "Country of origin")
    # detect common mismatched country phrases
    detected = []
    for country, variants in COUNTRY_SYNONYMS.items():
        if any(compact_for_match(v) in compact for v in variants):
            detected.append(country.title())
    evidence = f"Detected possible countries: {', '.join(detected) if detected else 'none'}"
    return FieldResult("Country of origin", expected, "Fail", 0, "Expected country of origin was not found.", evidence, "Country of origin")


def government_warning_check(ocr_text: str) -> FieldResult:
    text = normalize_text(ocr_text)
    compact = compact_for_match(text)
    expected_compact = compact_for_match(STANDARD_GOV_WARNING)
    has_header_exact = "GOVERNMENT WARNING:" in text
    has_header_any_case = "government warning" in text.lower()
    warning_score = fuzz.partial_ratio(expected_compact, compact) if compact else 0
    has_pregnancy = "pregnancy" in compact and "birth defects" in compact
    has_drive = "drive" in compact and "machinery" in compact and "health problems" in compact
    issues = []
    if not has_header_exact:
        issues.append("Header is missing or not exactly uppercase as 'GOVERNMENT WARNING:'.")
    if warning_score < 90:
        issues.append("Required warning text was not detected word-for-word with high confidence.")
    if not has_pregnancy:
        issues.append("Pregnancy/birth-defects clause was not clearly detected.")
    if not has_drive:
        issues.append("Driving/machinery/health-problems clause was not clearly detected.")
    if not issues:
        return FieldResult("Government warning", STANDARD_GOV_WARNING, "Pass", round(float(warning_score),1), "Government warning text and uppercase header appear compliant.", _nearest_snippet("GOVERNMENT WARNING", ocr_text), "Government warning")
    if warning_score >= 75 or has_header_any_case:
        return FieldResult("Government warning", STANDARD_GOV_WARNING, "Review", round(float(warning_score),1), "Government warning may be present, but issues require review: " + " ".join(issues), _nearest_snippet("GOVERNMENT WARNING", ocr_text), "Government warning")
    return FieldResult("Government warning", STANDARD_GOV_WARNING, "Fail", round(float(warning_score),1), "Government warning is missing or substantially incomplete: " + " ".join(issues), _nearest_snippet("GOVERNMENT WARNING", ocr_text), "Government warning")


def run_verification(expected: Dict[str, str], ocr_text: str) -> List[FieldResult]:
    return [
        fuzzy_field_check("Brand name", expected.get("brand_name", ""), ocr_text, threshold=87, review_threshold=68),
        fuzzy_field_check("Class/type", expected.get("class_type", ""), ocr_text, threshold=86, review_threshold=68),
        alcohol_content_check(expected.get("alcohol_content", ""), ocr_text),
        net_contents_check(expected.get("net_contents", ""), ocr_text),
        fuzzy_field_check("Bottler/producer", expected.get("bottler_producer", ""), ocr_text, threshold=82, review_threshold=62),
        country_of_origin_check(expected.get("country_of_origin", ""), ocr_text),
        government_warning_check(ocr_text),
    ]


def overall_status(results: List[FieldResult], quality_warnings: list[str] | None = None) -> str:
    statuses = [r.status for r in results if r.status != "Not checked"]
    if any(s == "Fail" for s in statuses):
        return "Fail"
    if any(s == "Review" for s in statuses):
        return "Review"
    if quality_warnings:
        return "Review"
    if statuses:
        return "Pass"
    return "Not checked"


def primary_issue(results: List[FieldResult], quality_warnings: list[str] | None = None) -> str:
    if quality_warnings:
        return "Image quality"
    for r in results:
        if r.status == "Fail":
            return r.issue_category or r.field
    for r in results:
        if r.status == "Review":
            return r.issue_category or r.field
    return ""
