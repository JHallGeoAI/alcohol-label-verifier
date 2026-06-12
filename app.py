"""Alcohol LabelCheck Prototype v4.

Author: Jeff Hall, GISP
Copyright © 2026 Jeff Hall. All rights reserved.
Provided for evaluation and demonstration purposes.

Generative AI tools were used as a development aid. All design decisions,
implementation choices, testing, validation, and final deliverables were
reviewed and approved by the author.
"""

from __future__ import annotations

__author__ = "Jeff Hall, GISP"
__copyright__ = "Copyright © 2026 Jeff Hall. All rights reserved."
__license__ = "Evaluation and demonstration use only"
__version__ = "4.0"

import io
import time
import zipfile
from typing import Dict, List

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

from src.ocr import run_ocr
from src.report import build_report, report_to_json, reports_to_csv, reports_to_dataframe
from src.rules import STANDARD_GOV_WARNING, run_verification

st.set_page_config(page_title="Alcohol LabelCheck Prototype v4", page_icon="🥃", layout="wide")

STATUS_ICON = {"Pass": "✅", "Review": "⚠️", "Fail": "❌", "Not checked": "➖"}
STATUS_COLORS = {"Pass": "#2E7D32", "Review": "#F9A825", "Fail": "#C62828", "Not checked": "#757575"}
FIELD_COLORS = {
    "Brand name": "#4E79A7",
    "Class/type": "#F28E2B",
    "Alcohol content": "#E15759",
    "Net contents": "#76B7B2",
    "Bottler/producer": "#59A14F",
    "Country of origin": "#EDC948",
    "Government warning": "#B07AA1",
    "Image quality": "#FF9DA7",
    "Missing uploaded file": "#9C755F",
}

st.title("Alcohol LabelCheck Prototype v4")
st.caption("Decision-support prototype with high-accuracy OCR, batch verification, CSV reports, confidence scoring, and an exception queue.")

with st.expander("Version 4 highlights", expanded=False):
    st.markdown(
        """
        - Inspector-friendly CSV remains the primary report output.
        - Batch dashboard uses semantic colors: green = pass, amber = review, red = fail.
        - High-accuracy multi-pass OCR is enabled by default because fast OCR failed 29 of 30 artistic batch labels.
        - Confidence score combines OCR field match scores and image-quality indicators.
        - Image quality score flags blur, low contrast, glare, and low resolution.
        - Exception queue filters the batch to only Review/Fail labels.
        - Evidence snippets show what OCR text supported each field decision.
        - JSON is retained only as optional technical evidence for future integration.
        """
    )


def expected_from_manual() -> Dict[str, str]:
    return {
        "beverage_type": st.session_state.get("beverage_type", "Distilled spirits"),
        "brand_name": st.session_state.get("brand_name", "OLD TOM DISTILLERY"),
        "class_type": st.session_state.get("class_type", "Kentucky Straight Bourbon Whiskey"),
        "alcohol_content": st.session_state.get("alcohol_content", "45% Alc./Vol. (90 Proof)"),
        "net_contents": st.session_state.get("net_contents", "750 mL"),
        "bottler_producer": st.session_state.get("bottler_producer", ""),
        "country_of_origin": st.session_state.get("country_of_origin", ""),
    }


def process_one(
    file,
    expected: Dict[str, str],
    high_accuracy: bool = True,
) -> Dict:
    """Process one label using the selected OCR mode.

    High-accuracy mode invokes the multi-pass OCR workflow directly. This avoids
    first running a separate fast pass and then repeating OCR in rescue mode.
    """
    total_start = time.perf_counter()
    file_bytes = file.getvalue()

    ocr_start = time.perf_counter()
    ocr_result = run_ocr(
        file_bytes,
        file.name,
        rescue=high_accuracy,
    )
    ocr_seconds = time.perf_counter() - ocr_start

    results = run_verification(expected, ocr_result.text)
    elapsed = time.perf_counter() - total_start

    report = build_report(
        file.name,
        expected,
        ocr_result.text,
        results,
        elapsed,
        quality=ocr_result.quality,
    )
    report["ocr_mode"] = (
        "High-accuracy multi-pass"
        if high_accuracy
        else "Fast single-pass"
    )
    report["ocr_seconds"] = round(ocr_seconds, 3)
    return report


def result_badge(status: str) -> str:
    return f"{STATUS_ICON.get(status, '')} {status}"


def render_status_chart(df: pd.DataFrame):
    if df.empty or "overall_status" not in df:
        return
    counts = df["overall_status"].fillna("Not checked").value_counts().reset_index()
    counts.columns = ["status", "count"]
    chart = (
        alt.Chart(counts)
        .mark_bar(cornerRadiusTopLeft=7, cornerRadiusTopRight=7)
        .encode(
            x=alt.X("status:N", title="Verification status", sort=["Pass", "Review", "Fail", "Not checked"]),
            y=alt.Y("count:Q", title="Labels"),
            color=alt.Color("status:N", scale=alt.Scale(domain=list(STATUS_COLORS.keys()), range=list(STATUS_COLORS.values())), legend=None),
            tooltip=["status", "count"],
        )
        .properties(height=270)
    )
    st.altair_chart(chart, use_container_width=True)


def render_issue_chart(df: pd.DataFrame):
    if df.empty or "primary_issue" not in df:
        return
    issues = df[df["primary_issue"].fillna("") != ""]["primary_issue"].value_counts().reset_index()
    issues.columns = ["issue", "count"]
    if issues.empty:
        st.info("No issue categories detected in this batch.")
        return
    domain = list(FIELD_COLORS.keys())
    range_ = [FIELD_COLORS[k] for k in domain]
    chart = (
        alt.Chart(issues)
        .mark_bar(cornerRadiusTopRight=7, cornerRadiusBottomRight=7)
        .encode(
            y=alt.Y("issue:N", title="Issue category", sort="-x"),
            x=alt.X("count:Q", title="Labels"),
            color=alt.Color("issue:N", scale=alt.Scale(domain=domain, range=range_), legend=None),
            tooltip=["issue", "count"],
        )
        .properties(height=270)
    )
    st.altair_chart(chart, use_container_width=True)


def render_confidence_chart(df: pd.DataFrame):
    if df.empty or "confidence_score" not in df:
        return
    bins = pd.cut(df["confidence_score"].fillna(0), bins=[0, 60, 80, 90, 100], labels=["Low", "Medium", "High", "Very high"], include_lowest=True)
    out = bins.value_counts().reindex(["Low", "Medium", "High", "Very high"]).fillna(0).reset_index()
    out.columns = ["confidence", "count"]
    color_domain = ["Low", "Medium", "High", "Very high"]
    color_range = ["#C62828", "#F9A825", "#4E79A7", "#2E7D32"]
    chart = (
        alt.Chart(out)
        .mark_bar(cornerRadiusTopLeft=7, cornerRadiusTopRight=7)
        .encode(
            x=alt.X("confidence:N", title="Confidence band", sort=color_domain),
            y=alt.Y("count:Q", title="Labels"),
            color=alt.Color("confidence:N", scale=alt.Scale(domain=color_domain, range=color_range), legend=None),
            tooltip=["confidence", "count"],
        )
        .properties(height=240)
    )
    st.altair_chart(chart, use_container_width=True)


def make_json_zip(reports: List[Dict]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for report in reports:
            safe_name = report["filename"].rsplit(".", 1)[0].replace("/", "_").replace("\\", "_")
            z.writestr(f"{safe_name}_evidence.json", report_to_json(report))
    buf.seek(0)
    return buf.getvalue()


def render_batch_results(reports: List[Dict], df: pd.DataFrame) -> None:
    """Render saved batch results on every Streamlit rerun."""
    if df.empty:
        return

    total = len(df)
    pass_count = int((df["overall_status"] == "Pass").sum())
    review_count = int((df["overall_status"] == "Review").sum())
    fail_count = int((df["overall_status"] == "Fail").sum())
    avg_seconds = float(df["processing_seconds"].mean())
    avg_conf = (
        float(df["confidence_score"].mean())
        if "confidence_score" in df
        else 0.0
    )
    avg_quality = (
        float(df["image_quality_score"].mean())
        if "image_quality_score" in df
        else 0.0
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Labels processed", total)
    m2.metric("Pass", pass_count)
    m3.metric("Review", review_count)
    m4.metric("Fail", fail_count)
    m5.metric("Avg sec/label", f"{avg_seconds:.2f}")

    c1, c2 = st.columns(2)
    c1.metric("Avg confidence", f"{avg_conf:.1f}%")
    c2.metric("Avg image quality", f"{avg_quality:.1f}/100")

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.subheader("Pass / review / fail")
        render_status_chart(df)
    with chart_col2:
        st.subheader("Primary issue categories")
        render_issue_chart(df)

    st.subheader("Confidence distribution")
    render_confidence_chart(df)

    st.subheader("Batch report")
    display_df = df.copy()
    if "overall_status" in display_df:
        display_df.insert(
            1,
            "result",
            display_df["overall_status"].map(result_badge),
        )

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.download_button(
        "Download inspector CSV report",
        data=reports_to_csv(reports),
        file_name="verification_results.csv",
        mime="text/csv",
        use_container_width=True,
        key="download_batch_csv",
    )
    st.download_button(
        "Download optional JSON evidence ZIP",
        data=make_json_zip(reports),
        file_name="json_evidence_reports.zip",
        mime="application/zip",
        use_container_width=True,
        key="download_batch_json",
    )


def render_single_result(report: Dict) -> None:
    """Render a saved individual-label result on every Streamlit rerun."""
    status = report["overall_status"]

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Overall result",
        result_badge(status),
        f"{report['processing_seconds']:.2f} sec",
    )
    c2.metric(
        "Confidence",
        f"{report.get('confidence_score', 0):.1f}%",
    )
    c3.metric(
        "Image quality",
        f"{report.get('image_quality_score', 0):.1f}/100",
    )

    mode = report.get("ocr_mode", "Unknown")
    ocr_seconds = report.get("ocr_seconds", report.get("processing_seconds", 0))
    st.caption(
        f"OCR mode: {mode} | OCR processing: {ocr_seconds:.2f} sec"
    )

    q = report.get("image_quality") or {}
    if q.get("warnings"):
        st.warning(" ".join(q["warnings"]))

    results_df = pd.DataFrame(report.get("results", []))
    if not results_df.empty:
        results_df.insert(
            0,
            "result",
            results_df["status"].map(result_badge),
        )
        st.dataframe(
            results_df[
                [
                    "result",
                    "field",
                    "score",
                    "message",
                    "expected",
                    "evidence",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Evidence snippets")
    render_evidence_cards(report)

    st.download_button(
        "Download CSV report",
        data=reports_to_csv([report]),
        file_name="labelcheck_report.csv",
        mime="text/csv",
        use_container_width=True,
        key="download_single_csv",
    )

    st.download_button(
        "Download JSON evidence",
        data=report_to_json(report),
        file_name="labelcheck_evidence.json",
        mime="application/json",
        use_container_width=True,
        key="download_single_json",
    )

    with st.expander("Extracted OCR text"):
        st.text_area(
            "OCR output",
            report.get("extracted_text", ""),
            height=260,
            key="single_ocr_output",
        )


def render_evidence_cards(report: Dict):
    for item in report.get("results", []):
        status = item.get("status", "")
        with st.expander(f"{result_badge(status)} — {item.get('field', '')}", expanded=status in ["Fail", "Review"]):
            st.write(item.get("message", ""))
            st.caption(f"Confidence/match score: {item.get('score')}")
            st.code(item.get("evidence", "") or "No OCR evidence snippet available.", language="text")


tab_single, tab_batch, tab_exceptions, tab_template = st.tabs(["Single label", "Batch processing", "Exception queue", "CSV template"])

with tab_single:
    left, right = st.columns([0.42, 0.58], gap="large")
    with left:
        st.header("1. Expected application fields")
        st.selectbox("Beverage type", ["Distilled spirits", "Wine", "Malt beverage/beer", "Other"], key="beverage_type")
        st.text_input("Brand name", value="OLD TOM DISTILLERY", key="brand_name")
        st.text_input("Class/type", value="Kentucky Straight Bourbon Whiskey", key="class_type")
        st.text_input("Alcohol content", value="45% Alc./Vol. (90 Proof)", key="alcohol_content")
        st.text_input("Net contents", value="750 mL", key="net_contents")
        st.text_input("Name/address of bottler or producer", value="", key="bottler_producer")
        st.text_input("Country of origin, if imported", value="", key="country_of_origin")
        high_accuracy = st.checkbox(
            "Use high-accuracy OCR processing",
            value=True,
            key="single_high_accuracy",
            help=(
                "Recommended. Uses multiple image variants and OCR passes for "
                "decorative or imperfect labels. Fast mode is retained only for "
                "comparison because it failed 29 of 30 artistic batch labels."
            ),
        )
        st.caption(
            "High-accuracy OCR is the recommended default. It may take longer, "
            "but it produced substantially more reliable results in batch testing."
        )

        uploaded = st.file_uploader(
            "Upload one label image or PDF",
            type=["png", "jpg", "jpeg", "tif", "tiff", "pdf"],
            key="single_upload",
        )

    with right:
        st.header("2. Verification results")

        if uploaded is None:
            st.session_state.pop("last_single_report", None)
            st.warning("Upload a label to run verification.")
            st.code(STANDARD_GOV_WARNING, language="text")
        else:
            if uploaded.type and uploaded.type.startswith("image"):
                st.image(
                    Image.open(uploaded),
                    caption="Uploaded label",
                    width="stretch",
                )

            if st.button(
                "Run label verification",
                type="primary",
                use_container_width=True,
            ):
                try:
                    with st.spinner(
                        "Reading the label and checking required fields..."
                    ):
                        report = process_one(
                            uploaded,
                            expected_from_manual(),
                            high_accuracy=high_accuracy,
                        )
                    st.session_state["last_single_report"] = report
                except Exception as exc:
                    st.error(
                        "The label could not be processed. Confirm "
                        "Tesseract is installed or try a clearer image."
                    )
                    st.exception(exc)

            saved_single_report = st.session_state.get(
                "last_single_report"
            )

            if (
                saved_single_report
                and saved_single_report.get("filename") == uploaded.name
            ):
                render_single_result(saved_single_report)

with tab_batch:
    st.header("Batch processing")
    st.write("Upload multiple labels and a CSV with one expected-fields row per filename. CSV is the primary inspector report output.")
    batch_files = st.file_uploader("Upload label files", type=["png", "jpg", "jpeg", "tif", "tiff", "pdf"], accept_multiple_files=True, key="batch_files")
    expected_csv = st.file_uploader("Upload expected-fields CSV", type=["csv"], key="expected_csv")
    high_accuracy_batch = st.checkbox(
        "Use high-accuracy OCR processing for batch",
        value=True,
        key="batch_high_accuracy",
        help=(
            "Recommended. Multi-pass OCR substantially improves recognition of "
            "artistic labels. Disabling it enables fast single-pass benchmarking "
            "but may produce many false failures."
        ),
    )
    st.caption(
        "Demonstration testing: fast single-pass OCR failed 29 of 30 artistic "
        "labels; high-accuracy processing averaged 7.23 seconds per label."
    )

    required_cols = ["filename", "brand_name", "class_type", "alcohol_content", "net_contents", "bottler_producer", "country_of_origin"]

    if expected_csv is not None:
        expected_df = pd.read_csv(expected_csv).fillna("")
        st.subheader("Expected-fields preview")
        st.dataframe(expected_df.head(10), use_container_width=True, hide_index=True)
        missing_cols = [c for c in required_cols if c not in expected_df.columns]
        if missing_cols:
            st.error(f"CSV is missing required columns: {', '.join(missing_cols)}")
    else:
        expected_df = pd.DataFrame()

    if batch_files and expected_csv is not None and not expected_df.empty and not [c for c in required_cols if c not in expected_df.columns]:
        if st.button("Run batch verification", type="primary", use_container_width=True):
            reports: List[Dict] = []
            file_lookup = {f.name: f for f in batch_files}
            progress = st.progress(0)
            status_box = st.empty()
            for idx, row in expected_df.iterrows():
                filename = row["filename"]
                status_box.write(f"Processing {filename}...")
                file = file_lookup.get(filename)
                if file is None:
                    reports.append({
                        "filename": filename,
                        "generated_at_utc": "",
                        "processing_seconds": 0,
                        "overall_status": "Fail",
                        "confidence_score": 0,
                        "image_quality_score": 0,
                        "primary_issue": "Missing uploaded file",
                        "image_quality": None,
                        "expected_fields": row.to_dict(),
                        "results": [],
                        "extracted_text": "",
                        "prototype_note": "CSV row had no matching uploaded file.",
                    })
                else:
                    expected = {k: str(row.get(k, "")) for k in required_cols if k != "filename"}
                    reports.append(process_one(file, expected, high_accuracy=high_accuracy_batch))
                progress.progress((idx + 1) / len(expected_df))
            status_box.success("Batch verification complete.")
            st.session_state["last_batch_reports"] = reports
            df = reports_to_dataframe(reports)
            st.session_state["last_batch_df"] = df

    # This section is outside the Run Batch button.
    saved_reports = st.session_state.get(
        "last_batch_reports",
        [],
    )

    saved_df = st.session_state.get(
        "last_batch_df",
        pd.DataFrame(),
    )

    if not saved_df.empty:
        render_batch_results(
            saved_reports,
            saved_df,
        )

with tab_exceptions:
    st.header("Exception queue")
    st.write("After running a batch, this view shows only labels that need human attention.")
    df = st.session_state.get("last_batch_df", pd.DataFrame())
    reports = st.session_state.get("last_batch_reports", [])
    if df.empty:
        st.info("Run a batch first to populate the exception queue.")
    else:
        exceptions = df[df["overall_status"].isin(["Review", "Fail"])].copy()
        st.metric("Exceptions needing review", len(exceptions))
        if exceptions.empty:
            st.success("No Review or Fail labels in the latest batch.")
        else:
            exceptions.insert(1, "result", exceptions["overall_status"].map(result_badge))
            st.dataframe(exceptions, use_container_width=True, hide_index=True)
            selected = st.selectbox("Open evidence for label", exceptions["filename"].tolist())
            report_lookup = {r["filename"]: r for r in reports}
            if selected in report_lookup:
                report = report_lookup[selected]
                st.subheader(selected)
                st.write(f"Result: **{result_badge(report['overall_status'])}** | Confidence: **{report.get('confidence_score', 0):.1f}%** | Issue: **{report.get('primary_issue', '')}**")
                render_evidence_cards(report)
                with st.expander("OCR text for this label"):
                    st.text_area("Extracted text", report.get("extracted_text", ""), height=260)
            st.download_button("Download exception-only CSV", data=exceptions.to_csv(index=False), file_name="exception_queue.csv", mime="text/csv", use_container_width=True)

with tab_template:
    st.header("Expected-fields CSV template")
    template = pd.DataFrame([
        {
            "filename": "example_label.png",
            "brand_name": "Old Tom Distillery",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "alcohol_content": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "bottler_producer": "Old Tom Distillery, 101 Barrelhouse Road, Frankfort, KY 40601",
            "country_of_origin": "",
        },
        {
            "filename": "import_label.png",
            "brand_name": "Highland Stag",
            "class_type": "Single Malt Scotch Whisky",
            "alcohol_content": "43% Alc./Vol. (86 Proof)",
            "net_contents": "750 mL",
            "bottler_producer": "Federal Spirits Import Co., Baltimore, MD 21230",
            "country_of_origin": "Scotland",
        },
    ])
    st.dataframe(template, use_container_width=True, hide_index=True)
    st.download_button("Download CSV template", data=template.to_csv(index=False), file_name="expected_fields_template.csv", mime="text/csv", use_container_width=True)

st.divider()
st.caption(
    "Prototype assumptions: standalone proof of concept; no COLA integration; "
    "no permanent file storage; CSV is primary output; JSON evidence is optional "
    "for future technical integration."
)
st.caption(
    "Developed by Jeff Hall, GISP | Copyright © 2026 Jeff Hall. "
    "All rights reserved."
)
