-- Схема БД joboffer v1 на коміті vshfrost/joboffer@99a2007 (міграції 0001..0031 на Postgres 18.6).
-- Отримано: `pg_dump --schema-only --no-owner --no-privileges` без psql-команд \restrict / \unrestrict
-- і без `set_config('search_path', '')`. Лише схема, без даних. Використовує tests/integration/test_import_v1.py.
--
-- PostgreSQL database dump
--


-- Dumped from database version 18.6 (Debian 18.6-1.pgdg13+2)
-- Dumped by pg_dump version 18.6 (Debian 18.6-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.applications (
    job_id integer NOT NULL,
    user_id integer NOT NULL,
    status text NOT NULL,
    applied_on date NOT NULL,
    channel text NOT NULL,
    ats text,
    company_domains text[] DEFAULT '{}'::text[] NOT NULL,
    company_emails text[] DEFAULT '{}'::text[] NOT NULL,
    status_changed_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_applications_ats_known CHECK ((ats = ANY (ARRAY['greenhouse'::text, 'lever'::text, 'ashby'::text, 'workable'::text, 'smartrecruiters'::text, 'other'::text]))),
    CONSTRAINT ck_applications_channel_known CHECK ((channel = ANY (ARRAY['email'::text, 'ats'::text, 'linkedin'::text, 'referral'::text]))),
    CONSTRAINT ck_applications_status_known CHECK ((status = ANY (ARRAY['applied'::text, 'replied'::text, 'interview'::text, 'offer'::text, 'rejected'::text, 'withdrawn'::text])))
);


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    id integer NOT NULL,
    user_id integer NOT NULL,
    job_id integer NOT NULL,
    kind text NOT NULL,
    version integer NOT NULL,
    content jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    lint jsonb,
    photo_id integer,
    CONSTRAINT ck_documents_kind_known CHECK ((kind = ANY (ARRAY['cv'::text, 'cl'::text]))),
    CONSTRAINT ck_documents_version_positive CHECK ((version >= 1))
);


--
-- Name: documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.documents_id_seq OWNED BY public.documents.id;


--
-- Name: facts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.facts (
    id integer NOT NULL,
    user_id integer NOT NULL,
    kind text NOT NULL,
    text text NOT NULL,
    text_hash text NOT NULL,
    confirmed boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: facts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.facts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: facts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.facts_id_seq OWNED BY public.facts.id;


--
-- Name: interview_kits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.interview_kits (
    id integer NOT NULL,
    user_id integer NOT NULL,
    job_id integer NOT NULL,
    version integer NOT NULL,
    content jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_interview_kits_version_positive CHECK ((version >= 1))
);


--
-- Name: interview_kits_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.interview_kits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: interview_kits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.interview_kits_id_seq OWNED BY public.interview_kits.id;


--
-- Name: job_analyses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_analyses (
    job_id integer NOT NULL,
    user_id integer NOT NULL,
    score integer NOT NULL,
    work_mode text,
    filters_passed boolean NOT NULL,
    flags text[] DEFAULT '{}'::text[] NOT NULL,
    details jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_job_analyses_score_range CHECK (((score >= 0) AND (score <= 100)))
);


--
-- Name: job_replies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_replies (
    id integer NOT NULL,
    user_id integer NOT NULL,
    mail_id integer NOT NULL,
    job_id integer,
    confidence text,
    matched_by text,
    suggested_type text NOT NULL,
    type text,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_job_replies_confidence_known CHECK ((confidence = ANY (ARRAY['high'::text, 'medium'::text, 'low'::text]))),
    CONSTRAINT ck_job_replies_matched_by_known CHECK ((matched_by = ANY (ARRAY['thread'::text, 'email'::text, 'domain'::text, 'ats'::text, 'name'::text]))),
    CONSTRAINT ck_job_replies_suggested_type_known CHECK ((suggested_type = ANY (ARRAY['auto_confirmation'::text, 'rejection'::text, 'invitation'::text, 'assignment'::text, 'other'::text]))),
    CONSTRAINT ck_job_replies_type_known CHECK ((type = ANY (ARRAY['auto_confirmation'::text, 'rejection'::text, 'invitation'::text, 'assignment'::text, 'other'::text])))
);


--
-- Name: job_replies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.job_replies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: job_replies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.job_replies_id_seq OWNED BY public.job_replies.id;


--
-- Name: job_triage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_triage (
    job_id integer NOT NULL,
    user_id integer NOT NULL,
    score integer NOT NULL,
    verdict text NOT NULL,
    reason text NOT NULL,
    triaged_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_job_triage_score_range CHECK (((score >= 0) AND (score <= 100))),
    CONSTRAINT ck_job_triage_verdict_known CHECK ((verdict = ANY (ARRAY['skip'::text, 'maybe'::text, 'analyse'::text])))
);


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    id integer NOT NULL,
    user_id integer NOT NULL,
    source text DEFAULT 'manual'::text NOT NULL,
    url text,
    title text,
    company text,
    text text,
    text_hash text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    linkedin_id text,
    opened_at timestamp with time zone,
    location text,
    dismissed_at timestamp with time zone,
    dismiss_reason text
);


--
-- Name: jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.jobs_id_seq OWNED BY public.jobs.id;


--
-- Name: mail_dropped; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mail_dropped (
    id integer NOT NULL,
    user_id integer NOT NULL,
    gmail_id text NOT NULL,
    reason text NOT NULL,
    received_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_mail_dropped_reason_known CHECK ((reason = ANY (ARRAY['daily_limit'::text, 'retired_tag'::text])))
);


--
-- Name: mail_dropped_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.mail_dropped_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mail_dropped_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.mail_dropped_id_seq OWNED BY public.mail_dropped.id;


--
-- Name: mail_inboxes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mail_inboxes (
    user_id integer NOT NULL,
    tag text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    rotated_at timestamp with time zone
);


--
-- Name: mail_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mail_messages (
    id integer NOT NULL,
    user_id integer NOT NULL,
    gmail_id text NOT NULL,
    message_id text DEFAULT ''::text NOT NULL,
    in_reply_to text DEFAULT ''::text NOT NULL,
    reference_ids text[] DEFAULT '{}'::text[] NOT NULL,
    from_address text DEFAULT ''::text NOT NULL,
    from_name text DEFAULT ''::text NOT NULL,
    to_addresses text[] DEFAULT '{}'::text[] NOT NULL,
    subject text DEFAULT ''::text NOT NULL,
    sent_at timestamp with time zone,
    received_at timestamp with time zone NOT NULL,
    category text NOT NULL,
    untrusted_text text DEFAULT ''::text NOT NULL,
    attachments jsonb NOT NULL,
    parse_error text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    sender_auth text DEFAULT 'unknown'::text NOT NULL,
    alerts_processed_at timestamp with time zone,
    CONSTRAINT ck_mail_messages_category_known CHECK ((category = ANY (ARRAY['company'::text, 'linkedin_alert'::text, 'linkedin_application'::text, 'linkedin_message'::text, 'forwarding_confirmation'::text, 'suspicious'::text, 'other'::text]))),
    CONSTRAINT ck_mail_messages_sender_auth_known CHECK ((sender_auth = ANY (ARRAY['verified'::text, 'failed'::text, 'unknown'::text])))
);


--
-- Name: mail_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.mail_messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mail_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.mail_messages_id_seq OWNED BY public.mail_messages.id;


--
-- Name: mail_retired_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mail_retired_tags (
    tag text NOT NULL,
    user_id integer NOT NULL,
    retired_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mail_sync_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mail_sync_requests (
    id integer NOT NULL,
    user_id integer NOT NULL,
    requested_at timestamp with time zone NOT NULL,
    handled_at timestamp with time zone
);


--
-- Name: mail_sync_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.mail_sync_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mail_sync_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.mail_sync_requests_id_seq OWNED BY public.mail_sync_requests.id;


--
-- Name: mail_sync_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mail_sync_state (
    mailbox text NOT NULL,
    history_id text,
    synced_at timestamp with time zone,
    last_error text DEFAULT ''::text NOT NULL,
    failed_at timestamp with time zone
);


--
-- Name: oauth_clients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.oauth_clients (
    client_id text NOT NULL,
    data jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: oauth_grants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.oauth_grants (
    key_hash text NOT NULL,
    kind text NOT NULL,
    user_id integer NOT NULL,
    data jsonb NOT NULL,
    expires_at bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: original_cvs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.original_cvs (
    user_id integer NOT NULL,
    file_name text,
    text text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: photos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.photos (
    id integer NOT NULL,
    user_id integer NOT NULL,
    label text DEFAULT ''::text NOT NULL,
    data bytea NOT NULL,
    width integer NOT NULL,
    height integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: photos_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.photos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: photos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.photos_id_seq OWNED BY public.photos.id;


--
-- Name: preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.preferences (
    user_id integer NOT NULL,
    roles text[] DEFAULT '{}'::text[] NOT NULL,
    work_modes text[] DEFAULT '{}'::text[] NOT NULL,
    relocation boolean DEFAULT false NOT NULL,
    seniority text[] DEFAULT '{}'::text[] NOT NULL,
    min_salary_eur integer,
    stop_words text[] DEFAULT '{}'::text[] NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    full_name text DEFAULT ''::text NOT NULL,
    email text DEFAULT ''::text NOT NULL,
    phone text DEFAULT ''::text NOT NULL,
    linkedin_url text DEFAULT ''::text NOT NULL,
    city text DEFAULT ''::text NOT NULL,
    github_url text DEFAULT ''::text NOT NULL,
    work_authorization text DEFAULT ''::text NOT NULL,
    title_keywords text[] DEFAULT '{}'::text[] NOT NULL,
    title_exclude text[] DEFAULT '{}'::text[] NOT NULL,
    include_unknown_mode boolean DEFAULT true NOT NULL,
    target_domains text[] DEFAULT '{}'::text[] NOT NULL,
    CONSTRAINT ck_preferences_min_salary_non_negative CHECK ((min_salary_eur >= 0))
);


--
-- Name: prep_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prep_attempts (
    id integer NOT NULL,
    question_id integer NOT NULL,
    grade integer NOT NULL,
    answer text DEFAULT ''::text NOT NULL,
    feedback text DEFAULT ''::text NOT NULL,
    box integer NOT NULL,
    answered_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_prep_attempts_box_range CHECK (((box >= 1) AND (box <= 5))),
    CONSTRAINT ck_prep_attempts_grade_range CHECK (((grade >= 0) AND (grade <= 5)))
);


--
-- Name: prep_attempts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.prep_attempts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: prep_attempts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.prep_attempts_id_seq OWNED BY public.prep_attempts.id;


--
-- Name: prep_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prep_questions (
    id integer NOT NULL,
    topic_id integer NOT NULL,
    question text NOT NULL,
    question_hash text NOT NULL,
    answer_points text[] NOT NULL,
    box integer NOT NULL,
    due_on date NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_prep_questions_box_range CHECK (((box >= 1) AND (box <= 5)))
);


--
-- Name: prep_questions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.prep_questions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: prep_questions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.prep_questions_id_seq OWNED BY public.prep_questions.id;


--
-- Name: prep_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prep_steps (
    id integer NOT NULL,
    topic_id integer NOT NULL,
    "position" integer NOT NULL,
    kind text NOT NULL,
    title text NOT NULL,
    details text DEFAULT ''::text NOT NULL,
    resources jsonb NOT NULL,
    minutes integer NOT NULL,
    done_at timestamp with time zone,
    note text DEFAULT ''::text NOT NULL,
    CONSTRAINT ck_prep_steps_kind_known CHECK ((kind = ANY (ARRAY['learn'::text, 'practice'::text, 'check'::text]))),
    CONSTRAINT ck_prep_steps_minutes_positive CHECK ((minutes > 0))
);


--
-- Name: prep_steps_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.prep_steps_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: prep_steps_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.prep_steps_id_seq OWNED BY public.prep_steps.id;


--
-- Name: prep_topic_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prep_topic_jobs (
    topic_id integer NOT NULL,
    job_id integer NOT NULL,
    gap text NOT NULL
);


--
-- Name: prep_topics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.prep_topics (
    id integer NOT NULL,
    user_id integer NOT NULL,
    slug text NOT NULL,
    title text NOT NULL,
    kind text NOT NULL,
    summary text DEFAULT ''::text NOT NULL,
    deadline date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    ready_at timestamp with time zone,
    CONSTRAINT ck_prep_topics_kind_known CHECK ((kind = ANY (ARRAY['tech'::text, 'behavioral'::text, 'domain'::text])))
);


--
-- Name: prep_topics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.prep_topics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: prep_topics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.prep_topics_id_seq OWNED BY public.prep_topics.id;


--
-- Name: rss_feeds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rss_feeds (
    id integer NOT NULL,
    user_id integer NOT NULL,
    source text NOT NULL,
    query text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_rss_feeds_source_known CHECK ((source = ANY (ARRAY['dou'::text, 'djinni'::text])))
);


--
-- Name: rss_feeds_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rss_feeds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: rss_feeds_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rss_feeds_id_seq OWNED BY public.rss_feeds.id;


--
-- Name: search_locations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.search_locations (
    id integer NOT NULL,
    user_id integer NOT NULL,
    "position" integer NOT NULL,
    place text NOT NULL,
    aliases text[] DEFAULT '{}'::text[] NOT NULL,
    work_modes text[] NOT NULL,
    CONSTRAINT ck_search_locations_work_modes_known CHECK (((cardinality(work_modes) > 0) AND (work_modes <@ ARRAY['remote'::text, 'hybrid'::text, 'onsite'::text])))
);


--
-- Name: search_locations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.search_locations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: search_locations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.search_locations_id_seq OWNED BY public.search_locations.id;


--
-- Name: source_refresh_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_refresh_requests (
    id integer NOT NULL,
    user_id integer NOT NULL,
    requested_at timestamp with time zone NOT NULL,
    handled_at timestamp with time zone
);


--
-- Name: source_refresh_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.source_refresh_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: source_refresh_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.source_refresh_requests_id_seq OWNED BY public.source_refresh_requests.id;


--
-- Name: source_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_runs (
    user_id integer NOT NULL,
    source text NOT NULL,
    ran_at timestamp with time zone NOT NULL,
    found integer DEFAULT 0 NOT NULL,
    imported integer DEFAULT 0 NOT NULL,
    filtered integer DEFAULT 0 NOT NULL,
    duplicate integer DEFAULT 0 NOT NULL,
    completed integer DEFAULT 0 NOT NULL,
    error text DEFAULT ''::text NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: watchlist_companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.watchlist_companies (
    id integer NOT NULL,
    user_id integer NOT NULL,
    platform text NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_watchlist_companies_platform_known CHECK ((platform = ANY (ARRAY['greenhouse'::text, 'ashby'::text, 'lever'::text])))
);


--
-- Name: watchlist_companies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.watchlist_companies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: watchlist_companies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.watchlist_companies_id_seq OWNED BY public.watchlist_companies.id;


--
-- Name: documents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents ALTER COLUMN id SET DEFAULT nextval('public.documents_id_seq'::regclass);


--
-- Name: facts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facts ALTER COLUMN id SET DEFAULT nextval('public.facts_id_seq'::regclass);


--
-- Name: interview_kits id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_kits ALTER COLUMN id SET DEFAULT nextval('public.interview_kits_id_seq'::regclass);


--
-- Name: job_replies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_replies ALTER COLUMN id SET DEFAULT nextval('public.job_replies_id_seq'::regclass);


--
-- Name: jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs ALTER COLUMN id SET DEFAULT nextval('public.jobs_id_seq'::regclass);


--
-- Name: mail_dropped id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_dropped ALTER COLUMN id SET DEFAULT nextval('public.mail_dropped_id_seq'::regclass);


--
-- Name: mail_messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_messages ALTER COLUMN id SET DEFAULT nextval('public.mail_messages_id_seq'::regclass);


--
-- Name: mail_sync_requests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_sync_requests ALTER COLUMN id SET DEFAULT nextval('public.mail_sync_requests_id_seq'::regclass);


--
-- Name: photos id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.photos ALTER COLUMN id SET DEFAULT nextval('public.photos_id_seq'::regclass);


--
-- Name: prep_attempts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_attempts ALTER COLUMN id SET DEFAULT nextval('public.prep_attempts_id_seq'::regclass);


--
-- Name: prep_questions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_questions ALTER COLUMN id SET DEFAULT nextval('public.prep_questions_id_seq'::regclass);


--
-- Name: prep_steps id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_steps ALTER COLUMN id SET DEFAULT nextval('public.prep_steps_id_seq'::regclass);


--
-- Name: prep_topics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_topics ALTER COLUMN id SET DEFAULT nextval('public.prep_topics_id_seq'::regclass);


--
-- Name: rss_feeds id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rss_feeds ALTER COLUMN id SET DEFAULT nextval('public.rss_feeds_id_seq'::regclass);


--
-- Name: search_locations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_locations ALTER COLUMN id SET DEFAULT nextval('public.search_locations_id_seq'::regclass);


--
-- Name: source_refresh_requests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_refresh_requests ALTER COLUMN id SET DEFAULT nextval('public.source_refresh_requests_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: watchlist_companies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_companies ALTER COLUMN id SET DEFAULT nextval('public.watchlist_companies_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: applications pk_applications; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT pk_applications PRIMARY KEY (job_id);


--
-- Name: documents pk_documents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT pk_documents PRIMARY KEY (id);


--
-- Name: facts pk_facts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facts
    ADD CONSTRAINT pk_facts PRIMARY KEY (id);


--
-- Name: interview_kits pk_interview_kits; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_kits
    ADD CONSTRAINT pk_interview_kits PRIMARY KEY (id);


--
-- Name: job_analyses pk_job_analyses; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_analyses
    ADD CONSTRAINT pk_job_analyses PRIMARY KEY (job_id);


--
-- Name: job_replies pk_job_replies; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_replies
    ADD CONSTRAINT pk_job_replies PRIMARY KEY (id);


--
-- Name: job_triage pk_job_triage; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_triage
    ADD CONSTRAINT pk_job_triage PRIMARY KEY (job_id);


--
-- Name: jobs pk_jobs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT pk_jobs PRIMARY KEY (id);


--
-- Name: mail_dropped pk_mail_dropped; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_dropped
    ADD CONSTRAINT pk_mail_dropped PRIMARY KEY (id);


--
-- Name: mail_inboxes pk_mail_inboxes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_inboxes
    ADD CONSTRAINT pk_mail_inboxes PRIMARY KEY (user_id);


--
-- Name: mail_messages pk_mail_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_messages
    ADD CONSTRAINT pk_mail_messages PRIMARY KEY (id);


--
-- Name: mail_retired_tags pk_mail_retired_tags; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_retired_tags
    ADD CONSTRAINT pk_mail_retired_tags PRIMARY KEY (tag);


--
-- Name: mail_sync_requests pk_mail_sync_requests; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_sync_requests
    ADD CONSTRAINT pk_mail_sync_requests PRIMARY KEY (id);


--
-- Name: mail_sync_state pk_mail_sync_state; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_sync_state
    ADD CONSTRAINT pk_mail_sync_state PRIMARY KEY (mailbox);


--
-- Name: oauth_clients pk_oauth_clients; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_clients
    ADD CONSTRAINT pk_oauth_clients PRIMARY KEY (client_id);


--
-- Name: oauth_grants pk_oauth_grants; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_grants
    ADD CONSTRAINT pk_oauth_grants PRIMARY KEY (key_hash);


--
-- Name: original_cvs pk_original_cvs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.original_cvs
    ADD CONSTRAINT pk_original_cvs PRIMARY KEY (user_id);


--
-- Name: photos pk_photos; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.photos
    ADD CONSTRAINT pk_photos PRIMARY KEY (id);


--
-- Name: preferences pk_preferences; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preferences
    ADD CONSTRAINT pk_preferences PRIMARY KEY (user_id);


--
-- Name: prep_attempts pk_prep_attempts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_attempts
    ADD CONSTRAINT pk_prep_attempts PRIMARY KEY (id);


--
-- Name: prep_questions pk_prep_questions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_questions
    ADD CONSTRAINT pk_prep_questions PRIMARY KEY (id);


--
-- Name: prep_steps pk_prep_steps; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_steps
    ADD CONSTRAINT pk_prep_steps PRIMARY KEY (id);


--
-- Name: prep_topic_jobs pk_prep_topic_jobs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_topic_jobs
    ADD CONSTRAINT pk_prep_topic_jobs PRIMARY KEY (topic_id, job_id);


--
-- Name: prep_topics pk_prep_topics; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_topics
    ADD CONSTRAINT pk_prep_topics PRIMARY KEY (id);


--
-- Name: rss_feeds pk_rss_feeds; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rss_feeds
    ADD CONSTRAINT pk_rss_feeds PRIMARY KEY (id);


--
-- Name: search_locations pk_search_locations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_locations
    ADD CONSTRAINT pk_search_locations PRIMARY KEY (id);


--
-- Name: source_refresh_requests pk_source_refresh_requests; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_refresh_requests
    ADD CONSTRAINT pk_source_refresh_requests PRIMARY KEY (id);


--
-- Name: source_runs pk_source_runs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_runs
    ADD CONSTRAINT pk_source_runs PRIMARY KEY (user_id, source);


--
-- Name: users pk_users; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT pk_users PRIMARY KEY (id);


--
-- Name: watchlist_companies pk_watchlist_companies; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_companies
    ADD CONSTRAINT pk_watchlist_companies PRIMARY KEY (id);


--
-- Name: documents uq_documents_job_id_kind_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT uq_documents_job_id_kind_version UNIQUE (job_id, kind, version);


--
-- Name: facts uq_facts_user_id_text_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facts
    ADD CONSTRAINT uq_facts_user_id_text_hash UNIQUE (user_id, text_hash);


--
-- Name: interview_kits uq_interview_kits_job_id_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_kits
    ADD CONSTRAINT uq_interview_kits_job_id_version UNIQUE (job_id, version);


--
-- Name: job_replies uq_job_replies_mail_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_replies
    ADD CONSTRAINT uq_job_replies_mail_id UNIQUE (mail_id);


--
-- Name: jobs uq_jobs_user_id_linkedin_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT uq_jobs_user_id_linkedin_id UNIQUE (user_id, linkedin_id);


--
-- Name: jobs uq_jobs_user_id_text_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT uq_jobs_user_id_text_hash UNIQUE (user_id, text_hash);


--
-- Name: jobs uq_jobs_user_id_url; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT uq_jobs_user_id_url UNIQUE (user_id, url);


--
-- Name: mail_dropped uq_mail_dropped_gmail_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_dropped
    ADD CONSTRAINT uq_mail_dropped_gmail_id UNIQUE (gmail_id);


--
-- Name: mail_inboxes uq_mail_inboxes_tag; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_inboxes
    ADD CONSTRAINT uq_mail_inboxes_tag UNIQUE (tag);


--
-- Name: mail_messages uq_mail_messages_gmail_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_messages
    ADD CONSTRAINT uq_mail_messages_gmail_id UNIQUE (gmail_id);


--
-- Name: prep_questions uq_prep_questions_topic_id_question_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_questions
    ADD CONSTRAINT uq_prep_questions_topic_id_question_hash UNIQUE (topic_id, question_hash);


--
-- Name: prep_steps uq_prep_steps_topic_id_position; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_steps
    ADD CONSTRAINT uq_prep_steps_topic_id_position UNIQUE (topic_id, "position");


--
-- Name: prep_topics uq_prep_topics_user_id_slug; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_topics
    ADD CONSTRAINT uq_prep_topics_user_id_slug UNIQUE (user_id, slug);


--
-- Name: rss_feeds uq_rss_feeds_user_id_source_query; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rss_feeds
    ADD CONSTRAINT uq_rss_feeds_user_id_source_query UNIQUE (user_id, source, query);


--
-- Name: watchlist_companies uq_watchlist_companies_user_id_platform_slug; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_companies
    ADD CONSTRAINT uq_watchlist_companies_user_id_platform_slug UNIQUE (user_id, platform, slug);


--
-- Name: ix_mail_dropped_user_id_reason_received_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mail_dropped_user_id_reason_received_at ON public.mail_dropped USING btree (user_id, reason, received_at);


--
-- Name: ix_mail_messages_user_id_received_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mail_messages_user_id_received_at ON public.mail_messages USING btree (user_id, received_at);


--
-- Name: ix_mail_sync_requests_user_id_requested_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mail_sync_requests_user_id_requested_at ON public.mail_sync_requests USING btree (user_id, requested_at);


--
-- Name: ix_source_refresh_requests_user_id_requested_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_source_refresh_requests_user_id_requested_at ON public.source_refresh_requests USING btree (user_id, requested_at);


--
-- Name: uq_search_locations_user_id_place; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_search_locations_user_id_place ON public.search_locations USING btree (user_id, lower(place));


--
-- Name: applications fk_applications_job_id_jobs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT fk_applications_job_id_jobs FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: applications fk_applications_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT fk_applications_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: documents fk_documents_job_id_jobs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_job_id_jobs FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: documents fk_documents_photo_id_photos; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_photo_id_photos FOREIGN KEY (photo_id) REFERENCES public.photos(id) ON DELETE SET NULL;


--
-- Name: documents fk_documents_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: facts fk_facts_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facts
    ADD CONSTRAINT fk_facts_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: interview_kits fk_interview_kits_job_id_jobs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_kits
    ADD CONSTRAINT fk_interview_kits_job_id_jobs FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: interview_kits fk_interview_kits_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_kits
    ADD CONSTRAINT fk_interview_kits_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: job_analyses fk_job_analyses_job_id_jobs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_analyses
    ADD CONSTRAINT fk_job_analyses_job_id_jobs FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: job_analyses fk_job_analyses_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_analyses
    ADD CONSTRAINT fk_job_analyses_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: job_replies fk_job_replies_job_id_jobs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_replies
    ADD CONSTRAINT fk_job_replies_job_id_jobs FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE SET NULL;


--
-- Name: job_replies fk_job_replies_mail_id_mail_messages; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_replies
    ADD CONSTRAINT fk_job_replies_mail_id_mail_messages FOREIGN KEY (mail_id) REFERENCES public.mail_messages(id) ON DELETE CASCADE;


--
-- Name: job_replies fk_job_replies_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_replies
    ADD CONSTRAINT fk_job_replies_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: job_triage fk_job_triage_job_id_jobs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_triage
    ADD CONSTRAINT fk_job_triage_job_id_jobs FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: job_triage fk_job_triage_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_triage
    ADD CONSTRAINT fk_job_triage_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: jobs fk_jobs_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT fk_jobs_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: mail_dropped fk_mail_dropped_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_dropped
    ADD CONSTRAINT fk_mail_dropped_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: mail_inboxes fk_mail_inboxes_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_inboxes
    ADD CONSTRAINT fk_mail_inboxes_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: mail_messages fk_mail_messages_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_messages
    ADD CONSTRAINT fk_mail_messages_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: mail_retired_tags fk_mail_retired_tags_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_retired_tags
    ADD CONSTRAINT fk_mail_retired_tags_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: mail_sync_requests fk_mail_sync_requests_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_sync_requests
    ADD CONSTRAINT fk_mail_sync_requests_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: oauth_grants fk_oauth_grants_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_grants
    ADD CONSTRAINT fk_oauth_grants_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: original_cvs fk_original_cvs_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.original_cvs
    ADD CONSTRAINT fk_original_cvs_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: photos fk_photos_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.photos
    ADD CONSTRAINT fk_photos_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: preferences fk_preferences_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preferences
    ADD CONSTRAINT fk_preferences_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: prep_attempts fk_prep_attempts_question_id_prep_questions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_attempts
    ADD CONSTRAINT fk_prep_attempts_question_id_prep_questions FOREIGN KEY (question_id) REFERENCES public.prep_questions(id) ON DELETE CASCADE;


--
-- Name: prep_questions fk_prep_questions_topic_id_prep_topics; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_questions
    ADD CONSTRAINT fk_prep_questions_topic_id_prep_topics FOREIGN KEY (topic_id) REFERENCES public.prep_topics(id) ON DELETE CASCADE;


--
-- Name: prep_steps fk_prep_steps_topic_id_prep_topics; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_steps
    ADD CONSTRAINT fk_prep_steps_topic_id_prep_topics FOREIGN KEY (topic_id) REFERENCES public.prep_topics(id) ON DELETE CASCADE;


--
-- Name: prep_topic_jobs fk_prep_topic_jobs_job_id_jobs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_topic_jobs
    ADD CONSTRAINT fk_prep_topic_jobs_job_id_jobs FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: prep_topic_jobs fk_prep_topic_jobs_topic_id_prep_topics; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_topic_jobs
    ADD CONSTRAINT fk_prep_topic_jobs_topic_id_prep_topics FOREIGN KEY (topic_id) REFERENCES public.prep_topics(id) ON DELETE CASCADE;


--
-- Name: prep_topics fk_prep_topics_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.prep_topics
    ADD CONSTRAINT fk_prep_topics_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: rss_feeds fk_rss_feeds_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rss_feeds
    ADD CONSTRAINT fk_rss_feeds_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: search_locations fk_search_locations_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_locations
    ADD CONSTRAINT fk_search_locations_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: source_refresh_requests fk_source_refresh_requests_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_refresh_requests
    ADD CONSTRAINT fk_source_refresh_requests_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: source_runs fk_source_runs_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_runs
    ADD CONSTRAINT fk_source_runs_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: watchlist_companies fk_watchlist_companies_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist_companies
    ADD CONSTRAINT fk_watchlist_companies_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


