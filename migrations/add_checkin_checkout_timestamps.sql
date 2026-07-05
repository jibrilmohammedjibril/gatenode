-- Add checked_in_at and checked_out_at columns to visitor_invites table
-- These track the actual timestamps when a visitor was checked in/out by security

ALTER TABLE visitor_invites
ADD COLUMN IF NOT EXISTS checked_in_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS checked_out_at TIMESTAMP WITH TIME ZONE;
