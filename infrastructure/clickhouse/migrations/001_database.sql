-- Migration 001: Create the sequoia database
-- Extracted from init/01_schema.sql for deploy-time idempotent migrations.

CREATE DATABASE IF NOT EXISTS sequoia;
