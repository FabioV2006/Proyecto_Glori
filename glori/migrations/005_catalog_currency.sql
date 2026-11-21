ALTER TABLE products ADD COLUMN currency text NOT NULL DEFAULT 'PEN'
    CHECK (currency ~ '^[A-Z]{3}$');
