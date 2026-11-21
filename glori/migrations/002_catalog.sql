CREATE TABLE products (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shop_id bigint NOT NULL REFERENCES shops(id),
    name text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('producto','servicio')),
    description text NOT NULL,
    brand text NOT NULL,
    unit text NOT NULL,
    supplier text NOT NULL DEFAULT '',
    image text NOT NULL,
    cash_price numeric(18,2) NOT NULL CHECK (cash_price >= 0),
    credit_price numeric(18,2) NOT NULL CHECK (credit_price > 0),
    single_allowed boolean NOT NULL,
    monthly_allowed boolean NOT NULL,
    active boolean NOT NULL DEFAULT true,
    CHECK (single_allowed OR monthly_allowed),
    UNIQUE (shop_id,id)
);

CREATE TABLE clients (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shop_id bigint NOT NULL REFERENCES shops(id),
    user_id bigint NOT NULL UNIQUE,
    name text NOT NULL,
    document text NOT NULL DEFAULT '',
    phone text NOT NULL DEFAULT '',
    email text NOT NULL DEFAULT '',
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    credit_limit numeric(18,2) NOT NULL CHECK (credit_limit >= 0),
    max_months smallint NOT NULL CHECK (max_months > 0),
    cutoff_day smallint NOT NULL CHECK (cutoff_day BETWEEN 1 AND 31),
    cutoff_time time NOT NULL,
    payment_day smallint NOT NULL CHECK (payment_day BETWEEN 1 AND 31),
    compensatory jsonb NOT NULL,
    moratory jsonb NOT NULL,
    UNIQUE (shop_id,id),
    FOREIGN KEY (shop_id,user_id) REFERENCES users(shop_id,id)
);
