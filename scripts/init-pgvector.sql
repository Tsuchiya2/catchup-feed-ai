-- Initialize pgvector extension and add AI-related columns to articles table
-- This script runs on first database initialization (via Docker entrypoint)

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_trgm for text search (if not already enabled)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Add embedding column to articles table (if it doesn't exist)
-- Note: The articles table is created by catchup-feed-backend
-- This script adds AI-specific columns

-- Check if table exists before altering
DO $$
BEGIN
    -- Add embedding column if it doesn't exist
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'articles') THEN
        IF NOT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = 'articles' AND column_name = 'embedding'
        ) THEN
            ALTER TABLE articles ADD COLUMN embedding vector(1536);
            RAISE NOTICE 'Added embedding column to articles table';
        END IF;

        -- Add category column if it doesn't exist
        IF NOT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = 'articles' AND column_name = 'category'
        ) THEN
            ALTER TABLE articles ADD COLUMN category VARCHAR(50);
            RAISE NOTICE 'Added category column to articles table';
        END IF;
    ELSE
        RAISE NOTICE 'articles table does not exist yet - will be created by catchup-feed-backend';
    END IF;
END $$;

-- Create IVFFlat index for cosine similarity search
-- Note: Index creation requires some data to be present
-- This will be created when there's enough data (or can be created manually later)
DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'articles') THEN
        IF EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = 'articles' AND column_name = 'embedding'
        ) THEN
            -- Check if index already exists
            IF NOT EXISTS (
                SELECT FROM pg_indexes
                WHERE tablename = 'articles' AND indexname = 'idx_articles_embedding'
            ) THEN
                -- IVFFlat index - requires data to be present
                -- Create with lists=100 (adjust based on data size: sqrt(rows))
                -- Note: For empty table, this will work but won't be effective until data is added
                CREATE INDEX IF NOT EXISTS idx_articles_embedding
                ON articles USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
                RAISE NOTICE 'Created IVFFlat index on embedding column';
            END IF;
        END IF;
    END IF;
END $$;

-- Create index on category for filtering
DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'articles') THEN
        IF EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = 'articles' AND column_name = 'category'
        ) THEN
            IF NOT EXISTS (
                SELECT FROM pg_indexes
                WHERE tablename = 'articles' AND indexname = 'idx_articles_category'
            ) THEN
                CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
                RAISE NOTICE 'Created index on category column';
            END IF;
        END IF;
    END IF;
END $$;

-- Verify setup
DO $$
BEGIN
    RAISE NOTICE 'pgvector extension version: %', (SELECT extversion FROM pg_extension WHERE extname = 'vector');
END $$;
