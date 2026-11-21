CREATE TABLE shops (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    timezone text NOT NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL UNIQUE CHECK (username = lower(username)),
    password_hash text NOT NULL,
    role text NOT NULL CHECK (role IN ('platform', 'shop', 'client')),
    shop_id bigint REFERENCES shops(id),
    active boolean NOT NULL DEFAULT true,
    CHECK ((role = 'platform') = (shop_id IS NULL)),
    UNIQUE (shop_id, id)
);
