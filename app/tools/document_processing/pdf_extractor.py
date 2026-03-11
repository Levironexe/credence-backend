"""
PDF Extractor Tool

Extracts text content from uploaded PDF files using pdfplumber.
"""

import logging
from pathlib import Path
from typing import Dict, Any
from pydantic import BaseModel, Field
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads")


class PDFExtractorInput(BaseModel):
    """Input: file path or URL of the uploaded PDF."""
    file_path: str = Field(
        description="Path or filename of the uploaded PDF file"
    )


class PDFExtractor(BaseTool):
    """
    Extract text from a PDF file using pdfplumber.

    Handles multi-page PDFs and returns concatenated text from all pages.
    Works with bank statements, financial reports, and other document types.
    """

    @property
    def name(self) -> str:
        return "pdf_extractor"

    @property
    def description(self) -> str:
        return (
            "Extract text content from an uploaded PDF file. "
            "Returns the full text from all pages. "
            "Use this to read bank statements, financial reports, or other PDF documents."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return PDFExtractorInput

    async def execute(self, file_path: str = None, **kwargs) -> Dict[str, Any]:
        if file_path is None:
            file_path = kwargs.get("file_path", "")

        if not file_path:
            return {"success": False, "error": "file_path is required"}

        try:
            import pdfplumber
        except ImportError:
            return {"success": False, "error": "pdfplumber is not installed"}

        # Resolve file path — handle both filenames and full paths
        path = Path(file_path)
        if not path.exists():
            # Try in uploads directory
            path = UPLOAD_DIR / Path(file_path).name
        if not path.exists():
            # Try extracting filename from URL
            filename = file_path.split("/")[-1]
            path = UPLOAD_DIR / filename
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            all_text = []
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        all_text.append(text)

            full_text = "\n\n".join(all_text)
            page_count = len(all_text)

            logger.info(f"Extracted text from {page_count} pages of {path.name}")

            return {
                "success": True,
                "text": full_text,
                "pages": page_count,
                "filename": path.name,
                "message": f"Extracted text from {page_count} page(s)"
            }

        except Exception as e:
            logger.error(f"Failed to extract PDF text: {e}")
            return {"success": False, "error": f"PDF extraction failed: {str(e)}"}


# Singleton
pdf_extractor = PDFExtractor()
