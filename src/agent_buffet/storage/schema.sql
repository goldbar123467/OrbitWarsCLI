create table if not exists runs (
  id text primary key,
  created_at text not null,
  agent_path text not null,
  opponents text not null,
  games integer not null,
  metrics_json text not null,
  report_path text
);

create table if not exists mining_notes (
  id integer primary key autoincrement,
  created_at text not null,
  source text not null,
  command text not null,
  output_path text not null,
  summary text
);

create table if not exists agents (
  name text primary key,
  created_at text not null,
  config_path text not null,
  main_path text,
  notes text
);
