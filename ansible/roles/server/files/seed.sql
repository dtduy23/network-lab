CREATE TABLE IF NOT EXISTS lab_events (
    id integer PRIMARY KEY,
    event_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO lab_events (id, event_name) VALUES
    (1, 'DNS ready'), (2, 'Firewall ready'), (3, 'Backup demo')
ON CONFLICT (id) DO NOTHING;
