CREATE TABLE sales (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shop_id bigint NOT NULL,
    client_id bigint NOT NULL,
    sold_at timestamptz NOT NULL,
    cutoff_at timestamptz NOT NULL,
    reference_due date NOT NULL,
    currency text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('single','monthly')),
    months smallint NOT NULL,
    capital numeric(18,2) NOT NULL CHECK (capital > 0),
    financed_principal numeric(18,2) NOT NULL,
    principal_pending numeric(18,2) NOT NULL CHECK (principal_pending BETWEEN 0 AND financed_principal),
    grace_days integer NOT NULL,
    grace_interest numeric(18,2) NOT NULL,
    single_interest numeric(18,2) NOT NULL,
    interest_days integer NOT NULL,
    terms jsonb NOT NULL,
    UNIQUE (shop_id,id),
    FOREIGN KEY (shop_id,client_id) REFERENCES clients(shop_id,id)
);

CREATE INDEX sales_by_client ON sales (shop_id,client_id,cutoff_at);

CREATE TABLE sale_lines (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shop_id bigint NOT NULL,
    sale_id bigint NOT NULL,
    product_id bigint NOT NULL,
    product_name text NOT NULL,
    description text NOT NULL,
    unit text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    price numeric(18,2) NOT NULL,
    FOREIGN KEY (shop_id,sale_id) REFERENCES sales(shop_id,id),
    FOREIGN KEY (shop_id,product_id) REFERENCES products(shop_id,id)
);

CREATE TABLE installments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shop_id bigint NOT NULL,
    sale_id bigint NOT NULL,
    sequence smallint NOT NULL,
    due date NOT NULL,
    opening numeric(18,2) NOT NULL,
    interest numeric(18,2) NOT NULL,
    capital numeric(18,2) NOT NULL,
    amount numeric(18,2) NOT NULL,
    closing numeric(18,2) NOT NULL,
    UNIQUE (shop_id,id),
    UNIQUE (sale_id,sequence),
    FOREIGN KEY (shop_id,sale_id) REFERENCES sales(shop_id,id)
);
