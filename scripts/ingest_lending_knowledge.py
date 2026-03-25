"""
Knowledge Base Ingestion Script

Reads document files from knowledge_base/ folder, chunks them,
embeds via OpenAI text-embedding-3-small, and stores in pgvector.

This is a legit RAG ingestion pipeline:
  Files on disk → text extraction → chunking → embedding → pgvector

Usage:
    python scripts/ingest_lending_knowledge.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from app.services.rag_service import rag_service
from app.config import settings

# Path to knowledge base documents
KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent / "knowledge_base"

# Map filenames to metadata (source, title, category)
FILE_METADATA = {
    "law_32_2024_credit_institutions.md": {
        "source": "Law 32/2024/QH15",
        "title": "Law on Credit Institutions 2024",
        "category": "regulation",
        "jurisdiction": "vietnam",
    },
    "circular_39_2016_lending.md": {
        "source": "Circular 39/2016/TT-NHNN",
        "title": "Lending Transactions of Credit Institutions",
        "category": "regulation",
        "jurisdiction": "vietnam",
    },
    "circular_11_2021_asset_classification.md": {
        "source": "Circular 11/2021/TT-NHNN",
        "title": "Asset Classification and Risk Provisioning",
        "category": "regulation",
        "jurisdiction": "vietnam",
    },
    "circular_14_2025_basel_iii.md": {
        "source": "Circular 14/2025/TT-NHNN",
        "title": "Basel III Capital Adequacy",
        "category": "regulation",
        "jurisdiction": "vietnam",
    },
    "cic_credit_scoring.md": {
        "source": "CIC Framework",
        "title": "Vietnam CIC Credit Scoring (150-750)",
        "category": "regulation",
        "jurisdiction": "vietnam",
    },
    "law_14_2022_aml.md": {
        "source": "Law 14/2022/QH15",
        "title": "Anti-Money Laundering",
        "category": "regulation",
        "jurisdiction": "vietnam",
    },
    "law_19_2023_consumer_protection.md": {
        "source": "Law 19/2023/QH15",
        "title": "Consumer Protection",
        "category": "regulation",
        "jurisdiction": "vietnam",
    },
    "decree_94_2025_fintech_sandbox.md": {
        "source": "Decree 94/2025/ND-CP",
        "title": "Fintech Regulatory Sandbox",
        "category": "regulation",
        "jurisdiction": "vietnam",
    },
    "sme_classification_support.md": {
        "source": "SME Framework",
        "title": "SME Classification and Support",
        "category": "regulation",
        "jurisdiction": "vietnam",
    },
    "ai_credit_scoring_governance.md": {
        "source": "AI Governance",
        "title": "AI/ML in Credit Decisions",
        "category": "assessment_methodology",
        "jurisdiction": "vietnam",
    },
    "sme_lending_best_practices.md": {
        "source": "Lending Best Practices",
        "title": "SME Lending Best Practices",
        "category": "best_practice",
        "jurisdiction": "vietnam",
    },
}


def read_documents() -> list[tuple[str, dict]]:
    """
    Read all document files from knowledge_base/ folder.

    Returns list of (text_content, metadata) tuples.
    Supports .md and .txt files. PDFs would need pdfplumber.
    """
    documents = []

    # Read files with known metadata
    for filename, metadata in FILE_METADATA.items():
        filepath = KNOWLEDGE_BASE_DIR / filename
        if filepath.exists():
            text = filepath.read_text(encoding="utf-8")
            documents.append((text, metadata))
            print(f"  Read: {filename} ({len(text)} chars)")
        else:
            print(f"  SKIP: {filename} (not found)")

    # Also read any .md/.txt files not in FILE_METADATA (auto-detect)
    for filepath in sorted(KNOWLEDGE_BASE_DIR.glob("*.md")):
        if filepath.name not in FILE_METADATA and filepath.name != "DOCUMENTS_NEEDED.md":
            text = filepath.read_text(encoding="utf-8")
            # Auto-generate metadata from filename
            name_parts = filepath.stem.replace("_", " ").title()
            documents.append((text, {
                "source": name_parts,
                "title": name_parts,
                "category": "general",
                "jurisdiction": "vietnam",
            }))
            print(f"  Read (auto): {filepath.name} ({len(text)} chars)")

    for filepath in sorted(KNOWLEDGE_BASE_DIR.glob("*.txt")):
        text = filepath.read_text(encoding="utf-8")
        name_parts = filepath.stem.replace("_", " ").title()
        documents.append((text, {
            "source": name_parts,
            "title": name_parts,
            "category": "general",
            "jurisdiction": "vietnam",
        }))
        print(f"  Read (auto): {filepath.name} ({len(text)} chars)")

    # Read PDFs if pdfplumber is available
    pdf_files = list(KNOWLEDGE_BASE_DIR.glob("*.pdf"))
    if pdf_files:
        try:
            import pdfplumber

            for filepath in sorted(pdf_files):
                text_parts = []
                with pdfplumber.open(filepath) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)

                if text_parts:
                    text = "\n\n".join(text_parts)
                    name_parts = filepath.stem.replace("_", " ").title()
                    documents.append((text, {
                        "source": name_parts,
                        "title": name_parts,
                        "category": "regulation",
                        "jurisdiction": "vietnam",
                    }))
                    print(f"  Read (PDF): {filepath.name} ({len(text)} chars, {len(text_parts)} pages)")
        except ImportError:
            print(f"  WARN: pdfplumber not installed, skipping {len(pdf_files)} PDF file(s)")

    return documents


def chunk_documents(
    documents: list[tuple[str, dict]],
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    """
    Split documents into chunks for embedding.

    Uses RecursiveCharacterTextSplitter which splits on paragraph/sentence
    boundaries to maintain semantic coherence.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
    )

    all_chunks = []
    for text, metadata in documents:
        chunks = splitter.split_text(text)
        for i, chunk in enumerate(chunks):
            chunk_metadata = metadata.copy()
            chunk_metadata["chunk_index"] = i
            chunk_metadata["total_chunks"] = len(chunks)
            all_chunks.append(Document(
                page_content=chunk.strip(),
                metadata=chunk_metadata,
            ))

    return all_chunks


async def ingest_knowledge():
    """Main ingestion pipeline: read files → chunk → embed → store in pgvector."""
    print("=" * 60)
    print("Credence RAG Knowledge Base Ingestion")
    print("=" * 60)

    # Step 1: Read documents from disk
    print(f"\n[1/4] Reading documents from {KNOWLEDGE_BASE_DIR}/")
    documents = read_documents()

    if not documents:
        print("\nERROR: No documents found in knowledge_base/ folder.")
        print("Add .md, .txt, or .pdf files and re-run.")
        return

    print(f"\n  Total: {len(documents)} document(s) read")

    # Step 2: Chunk documents
    print(f"\n[2/4] Chunking documents (size={settings.rag_chunk_size}, overlap={settings.rag_chunk_overlap})")
    chunks = chunk_documents(documents, settings.rag_chunk_size, settings.rag_chunk_overlap)
    print(f"  Created {len(chunks)} chunks from {len(documents)} documents")

    # Step 3: Initialize RAG service (connects to pgvector, sets up embeddings)
    print(f"\n[3/4] Connecting to pgvector database")
    print(f"  Host: {settings.database_host}:{settings.database_port}")
    print(f"  Database: {settings.database_name}")
    print(f"  Embedding model: {settings.embedding_model} ({settings.embedding_dimensions}d)")
    await rag_service.initialize()
    print("  Connected successfully")

    # Step 4: Embed and store in pgvector (in batches to avoid API rate limits)
    BATCH_SIZE = 10
    print(f"\n[4/4] Embedding {len(chunks)} chunks and storing in pgvector (batch size={BATCH_SIZE})...")
    try:
        all_ids = []
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i : i + BATCH_SIZE]
            ids = await rag_service.add_documents(batch)
            all_ids.extend(ids)
            print(f"  Batch {i // BATCH_SIZE + 1}: stored {len(ids)} embeddings ({len(all_ids)}/{len(chunks)})")
        ids = all_ids
        print(f"  Stored {len(ids)} embeddings in collection 'lending_knowledge'")
    except Exception as e:
        print(f"\n  ERROR during ingestion: {e}")
        print("\n  Troubleshooting:")
        print("  1. Is pgvector extension enabled? Run: CREATE EXTENSION IF NOT EXISTS vector;")
        print("  2. Is the database reachable?")
        print("  3. Is OPENAI_API_KEY set in .env?")
        raise

    # Test retrieval
    print("\n" + "=" * 60)
    print("Verification — Test Retrievals")
    print("=" * 60)

    test_queries = [
        "What are the lending limits under Vietnam's Law on Credit Institutions?",
        "What is the CIC credit score range?",
        "What provisions are required for Group 3 sub-standard loans?",
        "What does our lending policy say about past defaults?",
        "What are the AML requirements for customer due diligence?",
        "How are SMEs classified in Vietnam?",
    ]

    for query in test_queries:
        docs = await rag_service.retrieve(query, k=2)
        print(f"\nQ: {query}")
        if docs:
            top = docs[0]
            print(f"  -> {top.metadata.get('source')} — {top.metadata.get('title')}")
            print(f"     {top.page_content[:100]}...")
        else:
            print(f"  -> No results found")

    # Summary
    print("\n" + "=" * 60)
    print("Ingestion Summary")
    print("=" * 60)
    sources = set()
    for _, meta in documents:
        sources.add(f"{meta['source']} — {meta['title']}")
    for s in sorted(sources):
        print(f"  {s}")
    print(f"\n  Documents: {len(documents)}")
    print(f"  Chunks: {len(chunks)}")
    print(f"  Embeddings stored: {len(ids)}")
    print(f"\nDone.")


if __name__ == "__main__":
    asyncio.run(ingest_knowledge())
