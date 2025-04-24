# Docling Flyers

Experiment to use docling together with Granite 3.2 Vision model to parse PDF representing flyers of local general stores. This experiment is optimized to run in macOS.

## Execution

After dependencies are installed, you run:

`python docling_ocr.py [-v]`

## Installation

### Python

Python Dependencies

```
pyenv createvirtualenv 3.12 docling
pyenv activate docling
pip install docling tqdm ollama pypandoc
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
