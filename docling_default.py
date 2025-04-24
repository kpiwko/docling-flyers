import base64
import glob
import io
import logging
from pathlib import Path
import sys

from docling_core.types.doc import ImageRefMode
import ollama
import PIL.Image
import PIL.ImageOps
import pypandoc
from tqdm import tqdm

from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.models.tesseract_ocr_model import TesseractOcrOptions
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline

VISION_MODEL = "granite3.2-vision:2b"
DOCUMENT_LANGUAGES = ["ces", "slk", "eng"]

PROMPTS = {
    "cz": {
        "system": "Jsi asistent, který detailně popisuje obrázky. Pokud nevidíš nic konkrétního nebo nevíš, co s obrázkem dělat, vrať prázdný řětězec ''.",
        "image-description": "Popiš zlevněný/výhodný produkt z hypermarketu a pokud obrázek obsahuje text, vysvětli jej. "
        "Cena je v Kč a desetinná místa jsou oddělena čárkou nebo menším fontem.",
    },
    "en": {
        "system": "You are an assistant describing images consistently in high level of details. If you don't understand what is in the image and you down know what to do with the image, you return an empty string ''",
        "image-description": "Describe what general store product is on sale/offer and if the image contains text, explain it. "
        "Prices are in CZK and decimal places are divided by comma or are in a smaller font.",
    },
}

OUTPUT_DIR = "output"
IMAGE_RESOLUTION_SCALE = 2.0

logging.basicConfig(format="[%(levelname)s] leaflet: %(message)s", level=logging.INFO)
if "-v" in sys.argv:
    logging.getLogger().setLevel(logging.DEBUG)


LANGUAGE = "cz" if "-cz" in sys.argv else "en"
logging.info("Setting language to %s", LANGUAGE)

doc_paths = glob.glob("letaky/globus.pdf")
logging.debug("Processing %d files.", len(doc_paths))


def encode_image(image: PIL.Image.Image, format: str = "png") -> str:
    image = PIL.ImageOps.exif_transpose(image) or image
    image = image.convert("RGB")
    buffer = io.BytesIO()
    icc_profile = image.info.get("icc_profile")
    image.save(buffer, format, icc_profile=icc_profile)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


pipeline_options = PdfPipelineOptions(
    images_scale=IMAGE_RESOLUTION_SCALE,
    generate_page_images=True,
    generate_picture_images=True,
    do_ocr=True,
    # or ocr_options=OcrMacOptions(),
    ocr_options=TesseractOcrOptions(),
)

pipeline_options.ocr_options.lang = DOCUMENT_LANGUAGES

# Create the DocumentConverter and launch the conversion.
converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=pipeline_options,
            pipeline_cls=StandardPdfPipeline,
            backend=PyPdfiumDocumentBackend,
        )
    }
)

output_dir = Path("output")
output_dir.mkdir(parents=True, exist_ok=True)

PLACEHOLDER = "<replace-image-by-granite-description>"
for doc in tqdm(doc_paths):
    logging.info("Processing document from %s", doc)
    stem = Path(doc).stem
    result = converter.convert(doc)

    # convert pdf to markdown document using OCR and add placeholders for images
    text_content = result.document.export_to_markdown(
        image_mode=ImageRefMode.PLACEHOLDER, image_placeholder=PLACEHOLDER
    )
    images = result.document.pictures

    logging.info(
        "Document '%s' processed, extracted as %d characters of text and %d images. Using vision model to parse images",
        doc,
        len(text_content) - len(images) * len(PLACEHOLDER),
        len(images),
    )

    # process images in the document by vision model and replace placeholders with their description
    markdown_parsed = str(text_content)
    markdown_embedded = str(text_content)
    for pict in tqdm(images):
        ref = pict.get_ref().cref
        image = pict.get_image(result.document)

        if image:
            # image.show() # show the image in UI
            image_base64 = encode_image(image)

            response = ollama.chat(
                model=VISION_MODEL,
                messages=[
                    {"role": "system", "content": PROMPTS[LANGUAGE]["system"]},
                    {
                        "role": "user",
                        "content": PROMPTS[LANGUAGE]["image-description"],
                        "images": [image_base64],
                    },
                ],
            )
            description = response.message.content

            logging.debug("Image '%s' replaced with description: %s", ref, description)
            markdown_parsed = markdown_parsed.replace(PLACEHOLDER, description, 1)
            markdown_embedded = markdown_embedded.replace(
                PLACEHOLDER,
                f"![{description}](data:image/png;base64,{image_base64})",
                1,
            )

    for content, type in [(markdown_parsed, "parsed"), (markdown_embedded, "embedded")]:
        output_file = (
            output_dir
            / f"{stem}-{LANGUAGE}{'-embedded' if type == 'embedded' else ''}.md"
        )
        logging.info(
            "Markdown: original content of '%s' parsed into '%s' (chars: %d)%s",
            doc,
            output_file,
            len(content),
            " (with embedded images)" if type == "embedded" else "",
        )
        output_file.write_text(content)

        # output as html as well
        html_output_file = output_dir / f"{output_file.stem}.html"
        logging.info("Additionally storing as HTML in '%s'", html_output_file)
        html_content = pypandoc.convert_text(
            source=content,
            to="html",
            format="md",
            extra_args=[
                "--standalone",
                "--metadata=charset=UTF-8",
                f"--metadata=title='{stem} from Docling & Granite'",
            ],
        )
        html_output_file.write_text(html_content)
