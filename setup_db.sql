-- Create user if it doesn't exist
DO
$$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'toolkitrag') THEN
      CREATE USER toolkitrag WITH PASSWORD 'changeme';
   END IF;
END
$$;

-- Create database if it doesn't exist
SELECT 'CREATE DATABASE toolkitrag OWNER toolkitrag'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'toolkitrag')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE toolkitrag TO toolkitrag;

-- Connect to the database and create extension
\c toolkitrag

-- Create pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO toolkitrag;
