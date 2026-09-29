"""Initial schema after disposable test-data reset."""
from alembic import op

revision = "0001_user_accounts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE TABLE auth_rate_limits (\n\tkey_hash VARCHAR(64) NOT NULL, \n\twindow_started_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tattempts INTEGER NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (key_hash)\n)')
    op.execute('CREATE TABLE place_cache (\n\tcache_key VARCHAR(128) NOT NULL, \n\tprovider VARCHAR(32) NOT NULL, \n\tpayload JSONB NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (cache_key)\n)')
    op.execute('CREATE INDEX ix_place_cache_expires_at ON place_cache (expires_at)')
    op.execute('CREATE TABLE route_cache (\n\tcache_key VARCHAR(128) NOT NULL, \n\torigin_geohash VARCHAR(32) NOT NULL, \n\tdestination_place_id VARCHAR(128) NOT NULL, \n\ttravel_mode VARCHAR(32) NOT NULL, \n\tpayload JSONB NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (cache_key)\n)')
    op.execute('CREATE INDEX ix_route_cache_expires_at ON route_cache (expires_at)')
    op.execute('CREATE TABLE users (\n\tusername VARCHAR(32) NOT NULL, \n\tdisplay_name VARCHAR(40) NOT NULL, \n\tpassword VARCHAR(255) NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (username)\n)')
    op.execute('CREATE TABLE auth_sessions (\n\tuser_id UUID NOT NULL, \n\ttoken_hash VARCHAR(64) NOT NULL, \n\tcsrf_token VARCHAR(64) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tUNIQUE (token_hash)\n)')
    op.execute('CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id)')
    op.execute('CREATE TABLE discovery_sessions (\n\tuser_id UUID NOT NULL, \n\torigin_latitude FLOAT NOT NULL, \n\torigin_longitude FLOAT NOT NULL, \n\torigin_address VARCHAR(200) NOT NULL, \n\tbudget_per_person_min NUMERIC(10, 2), \n\tbudget_per_person_max NUMERIC(10, 2), \n\tmax_walking_minutes INTEGER NOT NULL, \n\tradius_meters INTEGER NOT NULL, \n\tpreferred_cuisines JSONB NOT NULL, \n\texcluded_cuisines JSONB NOT NULL, \n\tdesired_tags JSONB NOT NULL, \n\tmeal_period VARCHAR(32) NOT NULL, \n\tparty_size INTEGER NOT NULL, \n\topen_now_preferred BOOLEAN NOT NULL, \n\trequest_text VARCHAR(300) NOT NULL, \n\tnormalized_preferences JSONB NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)')
    op.execute('CREATE INDEX ix_discovery_sessions_user_id ON discovery_sessions (user_id)')
    op.execute('CREATE TABLE idempotency_records (\n\tuser_id UUID NOT NULL, \n\tendpoint VARCHAR(160) NOT NULL, \n\tidempotency_key VARCHAR(100) NOT NULL, \n\trequest_hash VARCHAR(128) NOT NULL, \n\tresponse_status INTEGER NOT NULL, \n\tresponse_body JSONB NOT NULL, \n\texpires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (user_id, endpoint, idempotency_key), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)')
    op.execute('CREATE INDEX ix_idempotency_records_user_id ON idempotency_records (user_id)')
    op.execute('CREATE TABLE preferences (\n\tuser_id UUID NOT NULL, \n\tpreferred_cuisines JSONB NOT NULL, \n\texcluded_cuisines JSONB NOT NULL, \n\tdisliked_places JSONB NOT NULL, \n\ttypical_budget_per_person_min NUMERIC(10, 2), \n\ttypical_budget_per_person_max NUMERIC(10, 2), \n\ttypical_max_walking_minutes INTEGER, \n\tpreferred_tags JSONB NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (user_id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)')
    op.execute('CREATE TABLE decision_runs (\n\tdiscovery_session_id UUID NOT NULL, \n\tparent_decision_id UUID, \n\tworkflow_version VARCHAR(32) NOT NULL, \n\tprompt_version VARCHAR(32) NOT NULL, \n\tstatus VARCHAR(32) NOT NULL, \n\trefinement_action VARCHAR(64) NOT NULL, \n\teffective_preferences JSONB NOT NULL, \n\tfilter_summary JSONB NOT NULL, \n\texcluded_place_keys JSONB NOT NULL, \n\tprovider VARCHAR(32) NOT NULL, \n\tmodel_provider VARCHAR(64) NOT NULL, \n\tmodel_name VARCHAR(128) NOT NULL, \n\tllm_used BOOLEAN NOT NULL, \n\tduration_ms INTEGER NOT NULL, \n\terror_code VARCHAR(64), \n\tcompleted_at TIMESTAMP WITHOUT TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(discovery_session_id) REFERENCES discovery_sessions (id), \n\tFOREIGN KEY(parent_decision_id) REFERENCES decision_runs (id)\n)')
    op.execute('CREATE INDEX ix_decision_runs_discovery_session_id ON decision_runs (discovery_session_id)')
    op.execute('CREATE INDEX ix_decision_runs_status ON decision_runs (status)')
    op.execute('CREATE TABLE decision_confirmations (\n\tdecision_run_id UUID NOT NULL, \n\tchanges JSONB NOT NULL, \n\tstatus VARCHAR(32) NOT NULL, \n\tresolved_at TIMESTAMP WITHOUT TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (decision_run_id), \n\tFOREIGN KEY(decision_run_id) REFERENCES decision_runs (id)\n)')
    op.execute('CREATE TABLE place_candidates (\n\tdecision_run_id UUID NOT NULL, \n\tplace_key VARCHAR(128) NOT NULL, \n\texternal_place_id VARCHAR(128) NOT NULL, \n\tname VARCHAR(150) NOT NULL, \n\tcategory_code VARCHAR(64) NOT NULL, \n\tcategory_name VARCHAR(200) NOT NULL, \n\tcuisine_types JSONB NOT NULL, \n\ttags JSONB NOT NULL, \n\taddress VARCHAR(250) NOT NULL, \n\tlatitude FLOAT NOT NULL, \n\tlongitude FLOAT NOT NULL, \n\tstraight_line_distance_meters INTEGER NOT NULL, \n\twalking_distance_meters INTEGER, \n\twalking_duration_seconds INTEGER, \n\trating FLOAT, \n\taverage_cost NUMERIC(10, 2), \n\tbusiness_status VARCHAR(16) NOT NULL, \n\topening_hours_text VARCHAR(200), \n\tphone VARCHAR(80), \n\tphotos JSONB NOT NULL, \n\tscore FLOAT NOT NULL, \n\tscore_breakdown JSONB NOT NULL, \n\trank INTEGER NOT NULL, \n\treason VARCHAR(600) NOT NULL, \n\twarnings JSONB NOT NULL, \n\tnavigation_url VARCHAR(1000), \n\troute_snapshot JSONB, \n\tplace_snapshot JSONB NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (decision_run_id, rank), \n\tUNIQUE (decision_run_id, place_key), \n\tFOREIGN KEY(decision_run_id) REFERENCES decision_runs (id)\n)')
    op.execute('CREATE INDEX candidate_run_score ON place_candidates (decision_run_id, score)')
    op.execute('CREATE INDEX ix_place_candidates_decision_run_id ON place_candidates (decision_run_id)')
    op.execute('CREATE TABLE tasks (\n\tdecision_run_id UUID NOT NULL, \n\tparent_task_id UUID, \n\tkind VARCHAR(32) NOT NULL, \n\tstatus VARCHAR(32) NOT NULL, \n\tphase VARCHAR(64) NOT NULL, \n\trequest_id VARCHAR(36) NOT NULL, \n\tstate JSONB NOT NULL, \n\tresult_refs JSONB NOT NULL, \n\tattempts INTEGER NOT NULL, \n\tlease_token VARCHAR(64), \n\tlease_until TIMESTAMP WITH TIME ZONE, \n\terror_code VARCHAR(64), \n\terror_message VARCHAR(500), \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(decision_run_id) REFERENCES decision_runs (id), \n\tFOREIGN KEY(parent_task_id) REFERENCES tasks (id)\n)')
    op.execute('CREATE INDEX ix_tasks_decision_run_id ON tasks (decision_run_id)')
    op.execute('CREATE INDEX ix_tasks_status ON tasks (status)')
    op.execute('CREATE INDEX task_claim_status_lease ON tasks (status, lease_until)')
    op.execute('CREATE INDEX task_run_created ON tasks (decision_run_id, created_at)')
    op.execute('CREATE TABLE place_choices (\n\tuser_id UUID NOT NULL, \n\tdiscovery_session_id UUID NOT NULL, \n\tplace_candidate_id UUID NOT NULL, \n\tfeedback VARCHAR(300) NOT NULL, \n\tidempotency_key VARCHAR(100) NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (user_id, idempotency_key), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(discovery_session_id) REFERENCES discovery_sessions (id), \n\tFOREIGN KEY(place_candidate_id) REFERENCES place_candidates (id)\n)')
    op.execute('CREATE INDEX ix_place_choices_user_id ON place_choices (user_id)')
    op.execute('CREATE TABLE task_events (\n\ttask_id UUID NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tevent_type VARCHAR(64) NOT NULL, \n\tpayload JSONB NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (task_id, sequence), \n\tFOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE\n)')
    op.execute('CREATE INDEX task_event_order ON task_events (task_id, sequence)')
    op.execute('CREATE TABLE task_steps (\n\ttask_id UUID NOT NULL, \n\tkey VARCHAR(128) NOT NULL, \n\tordinal INTEGER NOT NULL, \n\tstatus VARCHAR(32) NOT NULL, \n\tattempts INTEGER NOT NULL, \n\tinput_state JSONB NOT NULL, \n\toutput_state JSONB NOT NULL, \n\terror_code VARCHAR(64), \n\terror_message VARCHAR(500), \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (task_id, key), \n\tUNIQUE (task_id, ordinal), \n\tFOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE\n)')
    op.execute('CREATE INDEX task_step_status ON task_steps (task_id, status)')


def downgrade() -> None:
    op.drop_table("task_steps")
    op.drop_table("task_events")
    op.drop_table("place_choices")
    op.drop_table("tasks")
    op.drop_table("place_candidates")
    op.drop_table("decision_confirmations")
    op.drop_table("decision_runs")
    op.drop_table("preferences")
    op.drop_table("idempotency_records")
    op.drop_table("discovery_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
    op.drop_table("route_cache")
    op.drop_table("place_cache")
    op.drop_table("auth_rate_limits")
