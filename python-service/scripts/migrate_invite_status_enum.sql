-- Migration: Add 'sent' and 'failed' to invitestatus enum
-- Run once against the target PostgreSQL database.

-- Step 1: Add new values to the existing enum type
ALTER TYPE invitestatus ADD VALUE IF NOT EXISTS 'sent';
ALTER TYPE invitestatus ADD VALUE IF NOT EXISTS 'failed';

-- Step 2: Map old 'processing' rows that were already successfully sent.
-- Only do this if you can reliably identify them (e.g. by cross-referencing logs).
-- By default we leave 'processing' rows as-is so they get retried and resolved
-- to 'sent' or 'failed' by the new code path.
-- Uncomment the line below ONLY if you want to assume all current 'processing'
-- rows were sent successfully and should not be retried:
-- UPDATE meeting_invites SET status = 'sent' WHERE status = 'processing';
