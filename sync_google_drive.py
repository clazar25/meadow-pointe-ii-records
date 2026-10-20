
import io
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

import fitz
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

FOLDER_ID = "17JJOCAh3GKyvk9bkzPeV-PfHuCIlVLGu"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
OUTPUT = Path("drive-records.json")
PDF_DIR = Path("additional-public-records")


def safe_filename(name, file_id):
    stem = Path(name).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")
    return f"{stem[:80] or 'document'}-{file_id}.pdf"


def main():
    credentials_json = os.environ["GOOGLE_DRIVE_CREDENTIALS"]
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json),
        scopes=SCOPES,
    )
    drive = build("drive", "v3", credentials=credentials)

    query = (
        f"'{FOLDER_ID}' in parents "
        "and mimeType = 'application/pdf' and trashed = false"
    )

    files = []
    page_token = None

    while True:
        response = drive.files().list(
            q=query,
            fields="nextPageToken,files(id,name,modifiedTime)",
            pageSize=1000,
            pageToken=page_token,
        ).execute()

        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    PDF_DIR.mkdir(exist_ok=True)
    pages = []
    published_filenames = set()

    for file in sorted(files, key=lambda item: item["name"].lower()):
        file_id = file["id"]
        filename = safe_filename(file["name"], file_id)
        destination = PDF_DIR / filename

        buffer = io.BytesIO()
        request = drive.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        pdf_bytes = buffer.getvalue()

        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            extracted_pages = [
                page.get_text("text").strip()
                for page in document
            ]

        destination.write_bytes(pdf_bytes)
        published_filenames.add(filename)

        public_url = (
            "additional-public-records/"
            + quote(filename)
        )

        for page_number, page_text in enumerate(extracted_pages, start=1):
            pages.append({
                "source": file["name"],
                "url": public_url + f"#page={page_number}",
                "page": page_number,
                "text": page_text,
                "year": "",
                "type": "Additional Public Records",
                "category": "Additional Public Records",
            })

        print(f"Indexed {file['name']}: {len(extracted_pages)} pages")

    # Remove PDFs no longer present in the publishing folder.
    for existing in PDF_DIR.glob("*.pdf"):
        if existing.name not in published_filenames:
            existing.unlink()

    OUTPUT.write_text(
        json.dumps({"pages": pages}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Finished: {len(files)} PDFs, {len(pages)} pages")


if __name__ == "__main__":
    main()
