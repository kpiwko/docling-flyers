import glob
import logging
from pathlib import Path

import click
from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import (
    ApiVlmOptions,
    ResponseFormat,
    VlmPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline
from docling_core.types.doc import ImageRefMode
import pypdfium2 as pdfium
from tqdm import tqdm

OUTPUT_DIR = "output"
IMAGE_RESOLUTION_SCALE = 2.0
TIMEOUT = 600
MODEL = "gemma3:27b"


def count_pages(pdf_path):
    pdf = pdfium.PdfDocument(pdf_path)
    return len(pdf)


def get_vlm_options(model: str, prompt: str) -> ApiVlmOptions:
    return ApiVlmOptions(
        url="http://localhost:11434/v1/chat/completions",
        params={"model": MODEL},
        prompt=prompt,
        timeout=TIMEOUT,
        scale=IMAGE_RESOLUTION_SCALE,
        response_format=ResponseFormat.MARKDOWN,
    )


@click.command()
@click.option(
    "--lang",
    default="en",
    type=click.Choice(["en", "cz"]),
    show_default=True,
    help="Language for the prompt.",
)
@click.option("--verbose", is_flag=True, help="Enable verbose logging.")
@click.option(
    "--glob",
    "glob_pattern",
    default="flyers/two-pager.pdf",
    show_default=True,
    help="Glob pattern to select files.",
)
def main(lang: str, verbose: bool, glob_pattern: str):
    logging.basicConfig(
        format="[%(levelname)s] flyers: %(message)s",
        level=logging.DEBUG if verbose else logging.INFO,
    )

    doc_paths = glob.glob(glob_pattern)
    if not doc_paths:
        logging.error("No files matched the glob pattern: %s", glob_pattern)
        return

    logging.info("Found %d file(s) to process.", len(doc_paths))
    logging.info("Setting language to %s", lang)
    prompt = (
        "OCR the full page to markdown."
        if lang == "en"
        else "Použij OCR na celou stránku."
    )

    pipeline_options = VlmPipelineOptions(
        enable_remote_services=True,
        images_scale=IMAGE_RESOLUTION_SCALE,
        generate_page_images=False,
        generate_picture_images=True,
        vlm_options=get_vlm_options("gemma3:27b", prompt),
    )

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                pipeline_cls=VlmPipeline,
            )
        }
    )

    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    for doc in tqdm(doc_paths, desc="Docs", unit="doc"):
        logging.debug("Processing file: %s", doc)

        num_pages = count_pages(doc)
        results: list[ConversionResult] = []
        with tqdm(total=num_pages, desc="Page", unit="page") as pbar:
            for page in range(1, num_pages + 1):
                logging.debug("Processing page %d", page)
                result = converter.convert(
                    doc,
                    page_range=(page, page),  # Assuming 1-based indexing
                )
                results.append(result)
                pbar.update(1)

        combined_md = ""
        for result in results:
            combined_md += (
                result.document.export_to_markdown(
                    image_mode=ImageRefMode.PLACEHOLDER, image_placeholder=""
                )
                + "\n\n"
            )

        md_file = output_dir / f"{Path(doc).stem}-{lang}.md"
        logging.info("Writing Markdown to %s", md_file)
        md_file.write_text(combined_md)


if __name__ == "__main__":
    main()
