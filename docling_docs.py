import base64
import concurrent.futures
import glob as glob_module
import io
import logging
from pathlib import Path
import uuid

import click
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.models.tesseract_ocr_model import TesseractOcrOptions
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from docling_core.types.doc import ImageRefMode
from ollama import chat, ResponseError
import PIL.Image
import PIL.ImageOps
import pypandoc
from tqdm import tqdm

VISION_MODEL = "granite3.2-vision:2b"
GRAMMAR_MODEL = "gemma3:27b"
DOCUMENT_LANGUAGES = ["ces", "slk", "eng"]
TIMEOUT = 300
IMAGE_RESOLUTION_SCALE = 2.0
PLACEHOLDER = "<replace-image-by-vision-llm-description>"

PROMPTS = {
    "cz": {
        "image-system": "Jsi asistent, který detailně a konzistentně popisuje obrázky a grafy. Pokud nevidíš nic konkrétního "
        "nebo nevíš, co s obrázkem dělat, vrať prázdný řetězec ''.",
        "image-description": "Popiš obrázek, graf, zvýrazni důležité hodnoty a vysvětli jej. "
        "Částky jsou v Kč a desetinná místa jsou oddělena čárkou.",
        # "grammar-system": "Jsi uznávaný odborník, proslulý jako výjimečně talentovaný a efektivní copywriter v Češtině, "
        # "pečlivý textový editor a vážený redaktor New York Times. Opravuješ pravopisné, gramatické a faktické chyby v obsahu, "
        # "zlepšuješ srozumitelnost a zajišťuješ, že tvé psaní je uhlazené a profesionální. "
        # "Zachováváš původní hlas a tón textu. Dostaneš spropitné 1000 $, pokud odpovíš pouze opraveným textem a ničím jiným, "
        # "neposkytuj žádná vysvětlení, poznámky ani upřesnění.",
        # "grammar-fix": "Oprav překlepy, chybějící slabiky a slabiky navíc v textu, který následuje `---\n\n`. "
        # "Vrať celý text a HTML elementy neměň.",
    },
    "en": {
        "image-system": "You are an assistant describing images, charts and figures, consistently in high level of details. "
        "If you don't understand what is in the image and you down know what to do with the image, you return an empty string ''",
        "image-description": "Describe images, charts, figures, highlight important value, trends and explain it. "
        "Values are in CZK and decimal places are divided by comma.",
    },
}


def encode_image(image: PIL.Image.Image, format: str = "png") -> str:
    image = PIL.ImageOps.exif_transpose(image) or image
    image = image.convert("RGB")
    buffer = io.BytesIO()
    icc_profile = image.info.get("icc_profile")
    image.save(buffer, format, icc_profile=icc_profile)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def fix_grammar(text: str, language):
    try:
        response = chat(
            model=GRAMMAR_MODEL,
            messages=[
                {"role": "system", "content": PROMPTS[language]["grammar-system"]},
                {
                    "role": "user",
                    "content": PROMPTS[language]["grammar-fix"] + f": ---\n\n {text}",
                },
            ],
        )
        return response.message.content
    except ResponseError as e:
        logging.error("Error: %s", e)
        return str(e)


def vision_llm_describe(image_base64, language):
    try:
        response = chat(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": PROMPTS[language]["image-system"]},
                {
                    "role": "user",
                    "content": PROMPTS[language]["image-description"],
                    "images": [image_base64],
                },
            ],
        )
        return response.message.content
    except ResponseError as e:
        logging.error("Error: %s", e)
        return str(e)


def process_images(images, document, lang, no_vision, output_dir):
    """Returns (markdown_parsed, markdown_embedded).

    If no_vision=True, skips description lookup but still embeds images.
    """
    text_template = document.export_to_markdown(
        image_mode=ImageRefMode.PLACEHOLDER, image_placeholder=PLACEHOLDER
    )
    md_parsed = md_embedded = str(text_template)

    # We'll use a single-thread executor only when we actually need vision
    executor = (
        concurrent.futures.ThreadPoolExecutor(max_workers=1) if not no_vision else None
    )

    for pict in tqdm(images, desc="Image processing: ", unit="img"):
        ref = pict.get_ref().cref
        image = pict.get_image(document)
        if not image:
            continue

        b64 = encode_image(image)
        desc = PLACEHOLDER  # default fallback

        if executor:
            fut = executor.submit(vision_llm_describe, b64, lang)
            try:
                desc = fut.result(timeout=TIMEOUT)
            except concurrent.futures.TimeoutError:
                desc = f"[Timed out after {TIMEOUT}s]"
                path = output_dir / f"failed_image_{uuid.uuid4().hex}.png"
                image.save(path)
                logging.warning("Image %s timed out; saved to %s", ref, path)

        # replace one placeholder at a time
        md_parsed = md_parsed.replace(PLACEHOLDER, desc, 1)
        img_tag = f'<img alt="{desc}" src="data:image/png;base64,{b64}" />'
        md_embedded = md_embedded.replace(PLACEHOLDER, img_tag, 1)

    if executor:
        executor.shutdown()
    return md_parsed, md_embedded


def write_outputs(
    stem: str,
    lang: str,
    content: str,
    is_embedded: bool,
    output_dir: Path | str,
    no_html: bool,
):
    # if not is_embedded:
    #     logging.info("Fixing grammar with %s model", GRAMMAR_MODEL)
    #     content = fix_grammar(content, lang)

    suffix = "-embedded" if is_embedded else ""
    md_file = output_dir / f"{stem}-{lang}{suffix}.md"
    logging.info("Writing Markdown to %s", md_file)

    md_file.write_text(content)

    if not no_html:
        html_file = output_dir / f"{md_file.stem}.html"
        logging.info("Writing HTML to %s", html_file)
        html = pypandoc.convert_text(
            source=content,
            to="html",
            format="md",
            extra_args=[
                "--standalone",
                "--metadata=charset=UTF-8",
                f"--metadata=title={stem}",
            ],
        )
        html_file.write_text(html)


@click.command()
@click.option("--verbose", is_flag=True, help="Enable verbose logging.")
@click.option(
    "--glob", "input_glob", default="docs/*.pdf", help="Glob pattern for input files."
)
@click.option("--no-html", is_flag=True, help="Skip HTML output.")
@click.option("--no-vision", is_flag=True, help="Skip vision model image processing.")
@click.option(
    "--lang",
    default="en",
    type=click.Choice(["cz", "en"]),
    help="Language for prompts.",
)
def main(verbose: bool, input_glob: str, no_html: bool, no_vision: bool, lang: str):
    logging.basicConfig(
        format="[%(levelname)s] docs: %(message)s",
        level=logging.DEBUG if verbose else logging.INFO,
    )

    logging.info("Setting language to %s", lang)

    doc_paths = glob_module.glob(input_glob)
    logging.debug("Processing %d files.", len(doc_paths))

    pipeline_options = PdfPipelineOptions(
        images_scale=IMAGE_RESOLUTION_SCALE,
        generate_page_images=True,
        generate_picture_images=True,
        do_ocr=True,
        ocr_options=TesseractOcrOptions(),
    )

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

    for doc_path in tqdm(doc_paths, desc="Docs"):
        logging.info("Processing %s", doc_path)
        stem = Path(doc_path).stem
        result = converter.convert(doc_path)
        doc = result.document
        images = doc.pictures

        md_parsed, md_embedded = process_images(
            images=images,
            document=doc,
            lang=lang,
            no_vision=no_vision,
            output_dir=output_dir,
        )

        # write both variants
        write_outputs(stem, lang, md_parsed, False, output_dir, no_html)
        write_outputs(stem, lang, md_embedded, True, output_dir, no_html)


if __name__ == "__main__":
    main()
