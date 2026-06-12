# Alcohol LabelCheck Prototype v4

A Streamlit-based decision-support prototype developed to support TTB alcohol label review workflows by comparing label text against expected application fields. The application supports individual and batch label verification, adaptive multi-pass OCR, image-quality assessment, confidence scoring, an exception queue, CSV reporting, and optional JSON evidence exports.

## Author

**Jeff Hall, GISP**  
Copyright © 2026 Jeff Hall. All rights reserved.

This repository is provided for review, evaluation, and demonstration purposes. See `COPYRIGHT.md` for the project use notice.

## Features

- Individual PNG, JPG, TIFF, and PDF label processing
- Batch processing using multiple label files and an expected-fields CSV
- Fast OCR pass with conditional image-rescue processing
- Blur, low-contrast, glare, skew, and orientation handling
- Verification of brand name, class/type, alcohol content, net contents, bottler/producer information, country of origin, and government warning text
- Pass, Review, and Fail outcomes with evidence snippets
- Inspector-friendly CSV reports and an exception queue
- Dashboard metrics and color-coded charts

## Project structure

```text
alcohol-label-verifier/
├── app.py
├── requirements.txt
├── packages.txt
├── README.md
├── COPYRIGHT.md
├── sample_labels
├── .gitignore
└── src/
    ├── ocr.py
    ├── report.py
    ├── rules.py
    └── ...
```

Do not upload the local `.venv` directory, cached Python files, Streamlit secrets, or private assessment materials that are not intended for publication.

## Run locally on Windows

```powershell
cd C:\path\to\alcohol-label-verifier
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Tesseract OCR must be installed locally. The application should use the Windows executable when available and the system Tesseract command when deployed to Linux.

## Streamlit Community Cloud deployment

1. Upload the project to a GitHub repository.
2. Confirm that `app.py`, `requirements.txt`, `packages.txt`, and the `src` folder are at the expected repository paths.
3. Confirm that `packages.txt` contains `tesseract-ocr`.
4. In Streamlit Community Cloud, select **Create app**.
5. Select the repository and `main` branch.
6. Enter `app.py` as the entrypoint file.
7. Use Python 3.12 unless compatibility testing supports another version.
8. Deploy and review the build logs.
9. Test one clean label, one difficult label, and a batch before sharing the URL.

## Expected-fields CSV columns

```text
filename,brand_name,class_type,alcohol_content,net_contents,bottler_producer,country_of_origin
```

The `filename` value must exactly match the associated uploaded label filename.

## Performance approach

The application starts with a fast OCR pass. More expensive preprocessing and OCR rescue passes run only when required fields are missing, match scores are low, extracted text is limited, or the image quality indicates a potential problem. This adaptive approach is intended to improve typical response time while retaining robust handling for difficult images.

## Generative AI disclosure

Generative AI tools, including ChatGPT/OpenAI, were used as a development aid for brainstorming, code scaffolding, debugging support, synthetic test-data generation, and documentation drafting. All design decisions, implementation choices, testing, validation, and final deliverables were reviewed and approved by the author.

## Limitations

This prototype is a decision-support system, not an autonomous regulatory approval system. OCR results depend on source-image quality, text visibility, and layout complexity. Uncertain cases should be routed to a human reviewer.
