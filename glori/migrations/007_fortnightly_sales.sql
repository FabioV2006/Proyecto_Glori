ALTER TABLE sales DROP CONSTRAINT sales_mode_check;
ALTER TABLE sales ADD CONSTRAINT sales_mode_check CHECK (mode IN ('single','monthly','fortnightly'));
