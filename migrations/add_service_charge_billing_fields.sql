ALTER TABLE service_charge_configs ADD COLUMN due_day INTEGER DEFAULT 1;
ALTER TABLE service_charge_configs ADD COLUMN grace_period INTEGER DEFAULT 7;
