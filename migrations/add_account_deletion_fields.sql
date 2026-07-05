-- Migration: Add account deletion fields to users table
-- Date: 2026-02-15
-- Description: Add soft delete fields for 7-day grace period account deletion

ALTER TABLE users 
ADD COLUMN deletion_requested_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN scheduled_deletion_date TIMESTAMP WITH TIME ZONE,
ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE;

-- Add index for cleanup job efficiency
CREATE INDEX idx_users_scheduled_deletion 
ON users(scheduled_deletion_date) 
WHERE is_deleted = FALSE AND scheduled_deletion_date IS NOT NULL;

-- Add comment
COMMENT ON COLUMN users.deletion_requested_at IS 'When user requested account deletion';
COMMENT ON COLUMN users.scheduled_deletion_date IS 'When account will be permanently deleted (7 days after request)';
COMMENT ON COLUMN users.is_deleted IS 'True if account has been permanently deleted';
