import datetime
import glob
import logging
from pathlib import Path

from docling_core.types.doc import ImageRefMode
from tqdm import tqdm

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    ApiVlmOptions,
    ResponseFormat,
    VlmPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline

logging.basicConfig(format="[%(levelname)s] letak: %(message)s", level=logging.DEBUG)

OUTPUT_DIR = "output"
IMAGE_RESOLUTION_SCALE = 2.0

doc_paths = glob.glob("letaky/copy.pdf")
logging.debug("Processing %d files.", len(doc_paths))


def ollama_vlm_options(model: str, prompt: str):
    options = ApiVlmOptions(
        url="http://localhost:11434/v1/chat/completions",  # the default Ollama endpoint
        params=dict(
            model=model,
        ),
        prompt=prompt,
        timeout=180,
        scale=IMAGE_RESOLUTION_SCALE,
        response_format=ResponseFormat.MARKDOWN,
    )
    return options


pipeline_options = VlmPipelineOptions(
    enable_remote_services=True,  # <-- this is required!
    images_scale=IMAGE_RESOLUTION_SCALE,
    generate_page_images=False,
    generate_picture_images=True,
)

# The ApiVlmOptions() allows to interface with APIs supporting
# the multi-modal chat interface. Here follow a few example on how to configure those.

# One possibility is self-hosting model, e.g. via Ollama.
# Example using the Granite Vision  model
pipeline_options.vlm_options = ollama_vlm_options(
    model="granite3.2-vision:2b",
    prompt="OCR the full page to markdown.",
)

# Another possibility is using online services, e.g. watsonx.ai.
# Using requires setting the env variables WX_API_KEY and WX_PROJECT_ID.
# Uncomment the following line for this option:
# pipeline_options.vlm_options = watsonx_vlm_options(
#     model="ibm/granite-vision-3-2-2b", prompt="OCR the full page to markdown."
# )

# Create the DocumentConverter and launch the conversion.
converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=pipeline_options,
            pipeline_cls=VlmPipeline,
        )
    }
)

for doc in tqdm(doc_paths):
    logging.debug("%s processing", doc)
    result = converter.convert(doc)

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = datetime.datetime.now().strftime(
        f"{output_dir / Path(doc).name}-output-%Y-%m-%d_%H-%M.md"
    )
    result.document.save_as_markdown(
        Path(output_file), image_mode=ImageRefMode.REFERENCED
    )
