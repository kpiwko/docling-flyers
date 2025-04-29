# Docling Examples

Shows usage of `docling` together with Granite 3.2 Vision model to parse various PDF files.
These examples optimized to run in macOS.

- **Flyers** - representing flyers of local general stores in Czech language.
- **Docs** - representing structured PDF files in Czech language.

## Execution

After dependencies are installed, you run:

```
Usage: docling_flyers.py [OPTIONS]

Options:
  --verbose       Enable verbose logging.
  --glob TEXT     Glob pattern for input files.
  --no-html       Skip HTML output.
  --no-vision     Skip vision model image processing.
  --lang [cz|en]  Language for prompts.
  --help          Show this message and exit.
```

```
python docling_docs.py --help
Usage: docling_docs.py [OPTIONS]

Options:
  --verbose       Enable verbose logging.
  --glob TEXT     Glob pattern for input files.
  --no-html       Skip HTML output.
  --no-vision     Skip vision model image processing.
  --lang [cz|en]  Language for prompts.
  --help          Show this message and exit.
```

## Installation

### Python

Python Dependencies

```
pyenv createvirtualenv 3.12 docling
pyenv activate docling
pip install -r requirements.txt
```

### LLM dependecies

This experiments uses [ollama](https://ollama.com).

Get the model with `ollama pull granite3.2-vision:2b`.

### OCR Engines

Tessaract is used to OCR flyers in PDF format.

```

brew install tesseract leptonica pkg-config
TESSDATA_PREFIX=/opt/homebrew/share/tessdata/
echo "Set TESSDATA_PREFIX=${TESSDATA_PREFIX}"
brew install tesseract-lang
pip uninstall tesserocr
pip install --no-binary :all: tesserocr

```

### Pandoc

Pandoc is used to parse Markdown to HTML.

```
brew install pandoc
```

### Linters / Formatters

This repository has pre-commit hooks to lint and fix the code. You need to install it.

```
pip install isort black autoflake pre-commit
pre-commit install
```

You can run `pre-commit` manually on all files:

```
pre-commit run --all-files
```

In case you want to also fix the files, you can run:

```
pre-commit run --all-files --hook-stage manual
```
