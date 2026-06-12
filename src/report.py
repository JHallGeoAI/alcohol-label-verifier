from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Dict, List

import pandas as pd

from .rules import FieldResult, overall_status, primary_issue


def _field_confidence(results: List[FieldResult]) -> float:
    scored = []
    for r in results:
        if r.status == "Not checked":
            continue
        if r.score is None:
            continue
        scored.append(float(r.score))
    if not scored:
        return 0.0
    return round(sum(scored) / len(scored), 1)


def _quality_score(quality) -> float:
    if not quality:
        return 100.0
    # Simple inspector-facing score. It is intentionally heuristic.
    score = 100.0
    if quality.sharpness < 80:
        score -= 20
    elif quality.sharpness < 140:
        score -= 8
    if quality.contrast < 35:
        score -= 18
    elif quality.contrast < 50:
        score -= 6
    if quality.glare_percent > 12:
        score -= 20
    elif quality.glare_percent > 8:
        score -= 10
    if min(quality.width, quality.height) < 800:
        score -= 12
    return round(max(0.0, min(100.0, score)), 1)


def _overall_confidence(results: List[FieldResult], quality) -> float:
    field_score = _field_confidence(results)
    q_score = _quality_score(quality)
    if field_score == 0:
        return q_score
    # Weight field evidence more heavily than image quality.
    return round((field_score * 0.75) + (q_score * 0.25), 1)


def build_report(filename: str, expected: Dict[str, str], ocr_text: str, results: List[FieldResult], processing_seconds: float, quality=None) -> Dict:
    quality_warnings = quality.warnings if quality else []
    q_score = _quality_score(quality)
    confidence = _overall_confidence(results, quality)
    status = overall_status(results, quality_warnings)
    issue = primary_issue(results, quality_warnings)
    return {
        "filename": filename,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "processing_seconds": round(processing_seconds, 3),
        "overall_status": status,
        "confidence_score": confidence,
        "image_quality_score": q_score,
        "primary_issue": issue,
        "image_quality": quality.to_dict() if quality else None,
        "expected_fields": expected,
        "results": [r.to_dict() for r in results],
        "extracted_text": ocr_text,
        "prototype_note": "Agent-assist prototype only. Results should be reviewed by a compliance agent.",
    }


def report_to_json(report: Dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False)


def report_to_flat_row(report: Dict) -> Dict:
    row = {
        "filename": report["filename"],
        "overall_status": report["overall_status"],
        "confidence_score": report.get("confidence_score", ""),
        "image_quality_score": report.get("image_quality_score", ""),
        "primary_issue": report.get("primary_issue", ""),
        "processing_seconds": report.get("processing_seconds", ""),
    }
    q = report.get("image_quality") or {}
    row.update({
        "image_quality_warnings": "; ".join(q.get("warnings", []) or []),
        "sharpness": round(q.get("sharpness", 0), 1) if q else "",
        "contrast": round(q.get("contrast", 0), 1) if q else "",
        "glare_percent": round(q.get("glare_percent", 0), 1) if q else "",
    })
    for item in report.get("results", []):
        key = item["field"].lower().replace("/", "_").replace(" ", "_")
        row[f"{key}_status"] = item["status"]
        row[f"{key}_score"] = item["score"]
        row[f"{key}_message"] = item["message"]
        row[f"{key}_evidence"] = item["evidence"]
    return row


def reports_to_csv(reports: List[Dict]) -> str:
    rows = [report_to_flat_row(r) for r in reports]
    if not rows:
        return ""
    preferred = [
        "filename", "overall_status", "confidence_score", "image_quality_score", "primary_issue", "processing_seconds",
        "brand_name_status", "class_type_status", "alcohol_content_status", "net_contents_status",
        "bottler_producer_status", "country_of_origin_status", "government_warning_status",
        "image_quality_warnings", "sharpness", "contrast", "glare_percent",
    ]
    all_fields = sorted(set().union(*(row.keys() for row in rows)))
    fieldnames = [c for c in preferred if c in all_fields] + [c for c in all_fields if c not in preferred]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def reports_to_dataframe(reports: List[Dict]) -> pd.DataFrame:
    return pd.DataFrame([report_to_flat_row(r) for r in reports])
