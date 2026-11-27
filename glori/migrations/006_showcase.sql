CREATE TABLE showcase (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    shop_id bigint NOT NULL REFERENCES shops(id),
    merchant_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    FOREIGN KEY (shop_id, merchant_id) REFERENCES users(shop_id, id),
    FOREIGN KEY (shop_id, customer_id) REFERENCES users(shop_id, id)
);
