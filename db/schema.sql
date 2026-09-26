create extension if not exists postgis;
create table if not exists places (
 id text primary key, name text not null, category text not null,
 tagline text, description text, municipality text,
 lat double precision, lon double precision,
 location geography(point,4326) generated always as
 (case when lat is not null and lon is not null
 then st_setsrid(st_makepoint(lon,lat),4326)::geography end) stored,
 duration_class text, access_notes text, public_transport boolean,
 family_friendly boolean, seasonality text, restrictions text,
 source_url text, source_kind text, verification_status text not null,
 last_verified date
);
create index if not exists places_location_gix on places using gist(location);
create index if not exists places_category_idx on places(category);
