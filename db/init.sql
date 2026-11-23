CREATE TABLE IF NOT EXISTS upload_batches (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filename text NOT NULL,
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    raw_rows integer NOT NULL,
    unique_shipments integer NOT NULL DEFAULT 0,
    report jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS shipments_raw (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id bigint NOT NULL REFERENCES upload_batches(id),
    raw jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS shipments (
    shipment_id text PRIMARY KEY,
    mode text, container_mode text, carrier text,
    origin_port text, destination_port text, trade_lane text,
    shipper text, consignee text,
    etd date, eta date, atd date, ata date,
    weight_kg_raw numeric, weight_kg numeric, weight_ok boolean NOT NULL,
    volume_cbm numeric, status text,
    delay_days integer, dep_delay_days integer, is_valid_delivery boolean NOT NULL,
    max_severity text NOT NULL, issues text NOT NULL,
    upload_batch_id bigint NOT NULL REFERENCES upload_batches(id),
    raw_id bigint NOT NULL REFERENCES shipments_raw(id),
    flags jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS removed_duplicates (
    batch_id bigint NOT NULL REFERENCES upload_batches(id),
    shipment_id text NOT NULL,
    kept_raw_id bigint NOT NULL REFERENCES shipments_raw(id),
    dropped_raw_id bigint NOT NULL REFERENCES shipments_raw(id),
    reason text NOT NULL,
    PRIMARY KEY (batch_id, dropped_raw_id)
);
