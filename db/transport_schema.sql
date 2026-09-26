-- Transport layer for Peresheek.GO
create table if not exists transport_nodes (
  id text primary key,
  name text not null,
  type text not null,
  locality text,
  mode text not null,
  lat double precision,
  lon double precision,
  yandex_code text,
  last_verified date
);

create table if not exists place_transport (
  place_id text not null references places(id) on delete cascade,
  node_id text not null references transport_nodes(id) on delete cascade,
  last_mile_mode text,
  last_mile_km double precision,
  access_class text,
  notes text,
  primary key (place_id, node_id)
);

create index if not exists place_transport_node_idx on place_transport(node_id);
create index if not exists place_transport_access_idx on place_transport(access_class);

-- Timetables are intentionally not persisted here as permanent truth.
-- Fetch live departures/arrivals through the timetable provider API and use a short server cache.
