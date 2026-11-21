CREATE TABLE statements (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shop_id bigint NOT NULL,
    client_id bigint NOT NULL,
    cutoff_at timestamptz NOT NULL,
    due date NOT NULL,
    currency text NOT NULL,
    single_capital numeric(18,2) NOT NULL DEFAULT 0,
    single_interest numeric(18,2) NOT NULL DEFAULT 0,
    single_rate jsonb,
    UNIQUE (shop_id,id),
    UNIQUE (shop_id,client_id,cutoff_at,due,currency),
    FOREIGN KEY (shop_id,client_id) REFERENCES clients(shop_id,id)
);

CREATE TABLE statement_sales (
    shop_id bigint NOT NULL,
    statement_id bigint NOT NULL,
    sale_id bigint NOT NULL UNIQUE,
    PRIMARY KEY (statement_id,sale_id),
    FOREIGN KEY (shop_id,statement_id) REFERENCES statements(shop_id,id),
    FOREIGN KEY (shop_id,sale_id) REFERENCES sales(shop_id,id)
);

CREATE TABLE statement_installments (
    shop_id bigint NOT NULL,
    statement_id bigint NOT NULL,
    installment_id bigint NOT NULL UNIQUE,
    PRIMARY KEY (statement_id,installment_id),
    FOREIGN KEY (shop_id,statement_id) REFERENCES statements(shop_id,id),
    FOREIGN KEY (shop_id,installment_id) REFERENCES installments(shop_id,id)
);

CREATE TABLE payments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shop_id bigint NOT NULL,
    client_id bigint NOT NULL,
    idempotency_key text NOT NULL,
    paid_at timestamptz NOT NULL,
    currency text NOT NULL,
    amount numeric(18,2) NOT NULL CHECK (amount > 0),
    mora numeric(18,2) NOT NULL CHECK (mora >= 0),
    interest numeric(18,2) NOT NULL CHECK (interest >= 0),
    capital numeric(18,2) NOT NULL CHECK (capital >= 0),
    CHECK (amount = mora + interest + capital),
    UNIQUE (shop_id,id),
    UNIQUE (shop_id,client_id,idempotency_key),
    FOREIGN KEY (shop_id,client_id) REFERENCES clients(shop_id,id)
);

CREATE TABLE payment_allocations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shop_id bigint NOT NULL,
    payment_id bigint NOT NULL,
    statement_id bigint,
    installment_id bigint,
    days_late integer NOT NULL CHECK (days_late >= 0),
    mora numeric(18,2) NOT NULL CHECK (mora >= 0),
    interest numeric(18,2) NOT NULL CHECK (interest >= 0),
    capital numeric(18,2) NOT NULL CHECK (capital >= 0),
    CHECK ((statement_id IS NULL) <> (installment_id IS NULL)),
    UNIQUE (shop_id,statement_id),
    UNIQUE (shop_id,installment_id),
    FOREIGN KEY (shop_id,payment_id) REFERENCES payments(shop_id,id),
    FOREIGN KEY (shop_id,statement_id) REFERENCES statements(shop_id,id),
    FOREIGN KEY (shop_id,installment_id) REFERENCES installments(shop_id,id)
);
