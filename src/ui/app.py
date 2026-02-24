"""Gradio UI for the HIPAA Medical De-identification System."""

import logging
import time
import uuid
from collections import defaultdict
from pathlib import Path

import gradio as gr

logger = logging.getLogger(__name__)

_processing_history: list[dict] = []


def _get_pipeline(mode: str = "placeholder"):
    """Build a pipeline from the current settings."""
    from api.config import get_settings
    from redaction.factory import build_pipeline

    s = get_settings()
    return build_pipeline(
        provider=s.llm_provider,
        openai_api_key=s.openai_api_key,
        openai_model=s.openai_model,
        openai_temperature=s.openai_temperature,
        azure_endpoint=s.azure_openai_endpoint,
        api_key=s.azure_openai_api_key,
        deployment_name=s.azure_openai_deployment_name,
        api_version=s.azure_openai_api_version,
        enable_ocr=s.ocr_enabled,
        deidentification_mode=mode,
    )


def process_document(file_obj, mode, confidence):
    """Run the de-identification pipeline on an uploaded document."""
    if file_obj is None:
        raise gr.Error("Please upload a document first.")

    file_path = file_obj if isinstance(file_obj, str) else file_obj.name
    original_name = Path(file_path).name

    file_id = str(uuid.uuid4())[:12]
    from api.config import get_settings
    settings = get_settings()
    out_dir = Path(settings.storage_dir) / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(out_dir / f"{file_id}_deidentified.pdf")

    conf_threshold = int(confidence) if confidence else None
    config = {}
    if conf_threshold is not None:
        config["confidence_threshold"] = conf_threshold

    try:
        pipeline = _get_pipeline(mode)
        result = pipeline.process(
            input_path=file_path,
            output_path=output_path,
            config=config if config else None,
        )
    except Exception as e:
        raise gr.Error(f"De-identification failed: {e}")

    # Build "Before" panel — original PHI highlighted
    before_lines = []
    for f in result.findings:
        cat_label = f.category.replace("_", " ").title()
        before_lines.append(
            f"**Page {f.page_number + 1}** | `{cat_label}` | "
            f"<mark style='background:#fef3c7;padding:1px 4px;border-radius:3px'>"
            f"{f.text}</mark>  \n"
            f"<small style='color:#6b7280'>  {f.rationale} (conf {int(f.confidence * 100)}%)</small>"
        )
    before_md = "\n\n".join(before_lines) if before_lines else "*No PHI detected in this document.*"

    # Build "After" panel — de-identified replacements
    after_lines = []
    for f in result.findings:
        cat_label = f.category.replace("_", " ").title()
        replacement = f.replacement
        if not replacement:
            # Mask mode
            styled = (
                "<span style='background:#000;color:#000;padding:1px 6px;"
                "border-radius:3px;font-family:monospace'>REDACTED</span>"
            )
        elif replacement.startswith("["):
            # Placeholder mode
            styled = (
                f"<span style='background:#1e293b;color:white;padding:1px 6px;"
                f"border-radius:3px;font-family:monospace'>{replacement}</span>"
            )
        else:
            # Synthetic mode
            styled = (
                f"<span style='background:#dcfce7;color:#166534;padding:1px 6px;"
                f"border-radius:3px'>{replacement}</span>"
            )
        after_lines.append(f"**Page {f.page_number + 1}** | `{cat_label}` | {styled}")
    after_md = "\n\n".join(after_lines) if after_lines else "*Nothing to redact.*"

    # Findings table
    table_rows = []
    for f in result.findings:
        replacement = f.replacement or "(masked)"
        table_rows.append([
            f.page_number + 1,
            f.category.replace("_", " ").title(),
            f.subcategory.replace("_", " ").title(),
            f.text,
            replacement,
            f"{int(f.confidence * 100)}%",
            f.rationale,
        ])

    # Redaction report
    by_cat = defaultdict(int)
    for f in result.findings:
        by_cat[f.category.replace("_", " ").title()] += 1

    cat_rows = [[cat, count] for cat, count in sorted(by_cat.items(), key=lambda x: -x[1])]

    report_md = f"""### Redaction Report

| Metric | Value |
|--------|-------|
| **Total PHI Found** | {len(result.findings)} |
| **Redactions Applied** | {result.redacted_count} |
| **Processing Time** | {result.processing_time_seconds:.2f}s |
| **Pages Processed** | {result.total_pages} |
| **OCR Pages** | {result.ocr_pages} |
| **Mode** | {mode} |
"""
    if cat_rows:
        report_md += "\n### PHI Categories Breakdown\n\n| Category | Count |\n|----------|-------|\n"
        for cat, cnt in cat_rows:
            report_md += f"| {cat} | {cnt} |\n"

    # Store for dashboard
    cat_counts = {}
    for f in result.findings:
        cat = f.category if isinstance(f.category, str) else f.category.value
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    _processing_history.append({
        "file_id": file_id,
        "filename": original_name,
        "total_findings": len(result.findings),
        "total_redacted": result.redacted_count,
        "categories": cat_counts,
        "processing_time": round(result.processing_time_seconds, 2),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    })

    download_file = output_path if Path(output_path).exists() else None

    status_msg = (
        f"**De-identification complete** — "
        f"**{len(result.findings)}** PHI items found, "
        f"**{result.redacted_count}** redactions applied "
        f"in **{result.processing_time_seconds:.1f}s**"
    )

    return (
        status_msg,
        before_md,
        after_md,
        table_rows,
        report_md,
        download_file,
    )


def refresh_dashboard():
    """Build compliance dashboard from processing history."""
    if not _processing_history:
        return "### Compliance Dashboard\n\n*No documents processed yet.*", []

    total_docs = len(_processing_history)
    total_phi = sum(h["total_findings"] for h in _processing_history)
    total_redacted = sum(h["total_redacted"] for h in _processing_history)

    agg_cats = defaultdict(int)
    for h in _processing_history:
        for cat, cnt in h.get("categories", {}).items():
            agg_cats[cat] += cnt

    summary_md = f"""### Compliance Dashboard

| Metric | Value |
|--------|-------|
| **Documents Processed** | {total_docs} |
| **Total PHI Detected** | {total_phi} |
| **Total Redactions Applied** | {total_redacted} |

### PHI Detection by Category

| Category | Count | % |
|----------|-------|---|
"""
    for cat, cnt in sorted(agg_cats.items(), key=lambda x: -x[1]):
        pct = round(cnt / total_phi * 100, 1) if total_phi else 0
        label = cat.replace("_", " ").title()
        summary_md += f"| {label} | {cnt} | {pct}% |\n"

    recent_rows = []
    for h in reversed(_processing_history[-15:]):
        recent_rows.append([
            h["filename"],
            h["total_findings"],
            h["total_redacted"],
            f"{h.get('processing_time', '-')}s",
            h.get("timestamp", ""),
        ])

    return summary_md, recent_rows


CUSTOM_CSS = """
.gradio-container { max-width: 1200px !important; }
.status-banner { font-size: 1.05em; }
footer { display: none !important; }
"""


def create_ui() -> gr.Blocks:
    """Create and return the Gradio Blocks application."""
    with gr.Blocks(
        title="HIPAA Medical De-identification",
        theme=gr.themes.Soft(
            primary_hue="blue",
            secondary_hue="green",
            neutral_hue="slate",
        ),
        css=CUSTOM_CSS,
    ) as demo:

        gr.Markdown(
            """
            # HIPAA Medical De-identification System
            Upload a medical document, detect all HIPAA-defined Protected Health
            Information, and download a de-identified version.
            """
        )

        with gr.Tabs():

            with gr.Tab("De-identify", id="deidentify"):

                with gr.Row():
                    with gr.Column(scale=2):
                        file_input = gr.File(
                            label="Upload Medical Document",
                            file_types=[".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"],
                            type="filepath",
                        )
                    with gr.Column(scale=1):
                        mode_input = gr.Radio(
                            choices=["mask", "placeholder", "synthetic"],
                            value="placeholder",
                            label="De-identification Mode",
                            info="Mask: black box. Placeholder: [PATIENT_NAME] tags. Synthetic: realistic fake data.",
                        )
                        confidence_input = gr.Slider(
                            minimum=0, maximum=100, value=70, step=5,
                            label="Confidence Threshold (%)",
                            info="Only include findings above this confidence",
                        )
                        submit_btn = gr.Button(
                            "De-identify Document",
                            variant="primary",
                            size="lg",
                        )

                status_output = gr.Markdown(elem_classes=["status-banner"])

                gr.Markdown("### Before vs. After")

                with gr.Row(equal_height=True):
                    before_output = gr.Markdown(
                        label="Before (Original PHI Highlighted)",
                        value="*Upload a document to see results.*",
                    )
                    after_output = gr.Markdown(
                        label="After (De-identified)",
                        value="*Upload a document to see results.*",
                    )

                download_output = gr.File(label="Download De-identified PDF", interactive=False)

                gr.Markdown("### Detailed PHI Findings")
                findings_table = gr.Dataframe(
                    headers=["Page", "Category", "Subcategory", "Original Text",
                             "Replacement", "Confidence", "Rationale"],
                    datatype=["number", "str", "str", "str", "str", "str", "str"],
                    interactive=False,
                    wrap=True,
                )

            with gr.Tab("Redaction Report", id="report"):
                report_output = gr.Markdown(
                    value="*Process a document to see the redaction audit trail.*"
                )

            with gr.Tab("Compliance Dashboard", id="dashboard"):
                refresh_btn = gr.Button("Refresh Dashboard", size="sm")
                dashboard_md = gr.Markdown(
                    value="*No documents processed yet.*"
                )
                gr.Markdown("### Recent Uploads")
                recent_table = gr.Dataframe(
                    headers=["Filename", "PHI Found", "Redacted", "Time", "Timestamp"],
                    datatype=["str", "number", "number", "str", "str"],
                    interactive=False,
                    wrap=True,
                )

        submit_btn.click(
            fn=process_document,
            inputs=[file_input, mode_input, confidence_input],
            outputs=[
                status_output,
                before_output,
                after_output,
                findings_table,
                report_output,
                download_output,
            ],
        ).then(
            fn=refresh_dashboard,
            inputs=[],
            outputs=[dashboard_md, recent_table],
        )

        refresh_btn.click(
            fn=refresh_dashboard,
            inputs=[],
            outputs=[dashboard_md, recent_table],
        )

    return demo
