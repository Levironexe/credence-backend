-- Migration: Enable pgvector extension for RAG knowledge base
-- Date: 2026-03-25
-- Description: Enables the vector extension required by langchain-postgres PGVector.
-- Note: langchain-postgres auto-creates the collection tables, but the extension must exist first.

CREATE EXTENSION IF NOT EXISTS vector;
