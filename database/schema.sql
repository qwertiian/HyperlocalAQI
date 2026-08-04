-- Run this in the Supabase SQL editor (Project -> SQL Editor -> New query)
-- Enables PostGIS and creates the core tables used across all phases.

create extension if not exists postgis;

-- Ground monitoring stations (CPCB / OpenAQ)
create table if not exists stations (
    station_id      text primary key,
    name            text not null,
    source          text not null,              -- 'cpcb' | 'openaq'
    lat             double precision not null,
    lon             double precision not null,
    geom            geometry(Point, 4326),
    city            text,
    created_at      timestamptz default now()
);

-- Raw + cleaned pollutant readings, one row per station per timestamp per parameter
create table if not exists readings (
    id              bigserial primary key,
    station_id      text references stations(station_id),
    parameter       text not null,               -- pm25 | pm10 | no2 | so2 | co | o3 | aqi
    value           double precision not null,
    unit            text,
    recorded_at     timestamptz not null,
    ingested_at     timestamptz default now(),
    unique (station_id, parameter, recorded_at)
);

create index if not exists idx_readings_station_time on readings (station_id, recorded_at desc);
create index if not exists idx_readings_param_time on readings (parameter, recorded_at desc);

-- Weather covariates, joined to nearest station or a grid cell
create table if not exists weather (
    id              bigserial primary key,
    lat             double precision not null,
    lon             double precision not null,
    recorded_at     timestamptz not null,
    temperature_c   double precision,
    humidity_pct    double precision,
    wind_speed_ms   double precision,
    wind_dir_deg    double precision,
    boundary_layer_height_m double precision,
    source          text default 'open-meteo',
    unique (lat, lon, recorded_at)
);

-- Satellite AOD / trace-gas columns (Sentinel-5P via GEE), aggregated per grid cell/day
create table if not exists satellite_features (
    id              bigserial primary key,
    grid_lat        double precision not null,
    grid_lon        double precision not null,
    date            date not null,
    aerosol_index   double precision,
    no2_col         double precision,
    so2_col         double precision,
    co_col          double precision,
    source          text default 'sentinel-5p',
    unique (grid_lat, grid_lon, date)
);

-- Interpolated / forecasted surface output (what the dashboard reads)
create table if not exists aqi_predictions (
    id              bigserial primary key,
    lat             double precision not null,
    lon             double precision not null,
    predicted_at    timestamptz not null,       -- forecast target time
    generated_at    timestamptz default now(),
    horizon_hours   int not null default 0,      -- 0 = nowcast, 24/48/72 = forecast
    aqi_value       double precision not null,
    method          text not null,               -- idw | kriging | prophet | lstm | lstm+aod
    model_version   text
);

create index if not exists idx_predictions_time on aqi_predictions (predicted_at, horizon_hours);

-- User health profiles for the advisory layer
create table if not exists health_profiles (
    profile_id      text primary key,
    age_band        text,                        -- child | adult | elderly
    respiratory_condition boolean default false,
    cardiac_condition boolean default false,
    pregnant        boolean default false,
    activity_level  text,                         -- sedentary | moderate | outdoor_worker | athlete
    language        text default 'en'
);

-- Generated advisories, kept for the evaluation rubric table in the paper
create table if not exists advisories (
    id              bigserial primary key,
    profile_id      text references health_profiles(profile_id),
    aqi_value       double precision not null,
    aqi_category    text not null,
    advisory_text   text not null,
    generated_by    text not null,                -- template | gemini | ollama
    rater_1_score   int,
    rater_2_score   int,
    created_at      timestamptz default now()
);
