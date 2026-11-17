--
-- PostgreSQL database dump
--

\restrict szUMnyNRLyh6b3W1BvTghEYTthJm49RMYFenWPziQqHhQ5jWAPV312Charu96Ts

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: audits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audits (
    id integer NOT NULL,
    actor character varying(100),
    action character varying(200),
    created character varying(40)
);


--
-- Name: audits_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audits_id_seq OWNED BY public.audits.id;


--
-- Name: facts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.facts (
    id integer NOT NULL,
    class_code character varying(50) NOT NULL,
    day character varying(10) NOT NULL,
    mode character varying(20),
    enrolled integer,
    attended integer,
    completed integer,
    refunds integer,
    note text
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
-- Name: metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.metrics (
    id integer NOT NULL,
    code character varying(40) NOT NULL,
    version integer NOT NULL,
    name character varying(100),
    numerator character varying(200),
    denominator character varying(200),
    numerator_mode character varying(20),
    denominator_mode character varying(20),
    note text,
    locked boolean
);


--
-- Name: metrics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.metrics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.metrics_id_seq OWNED BY public.metrics.id;


--
-- Name: snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.snapshots (
    id integer NOT NULL,
    metric_id integer,
    baseline_id integer,
    date_from character varying(10),
    date_to character varying(10),
    state character varying(20),
    result json,
    error text,
    note text,
    approval character varying(20),
    approved_by character varying(100)
);


--
-- Name: snapshots_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.snapshots_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: snapshots_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.snapshots_id_seq OWNED BY public.snapshots.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    email character varying(100) NOT NULL,
    password character varying(200),
    role character varying(20)
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
-- Name: audits id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audits ALTER COLUMN id SET DEFAULT nextval('public.audits_id_seq'::regclass);


--
-- Name: facts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facts ALTER COLUMN id SET DEFAULT nextval('public.facts_id_seq'::regclass);


--
-- Name: metrics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrics ALTER COLUMN id SET DEFAULT nextval('public.metrics_id_seq'::regclass);


--
-- Name: snapshots id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshots ALTER COLUMN id SET DEFAULT nextval('public.snapshots_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: audits audits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audits
    ADD CONSTRAINT audits_pkey PRIMARY KEY (id);


--
-- Name: facts facts_class_code_day_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facts
    ADD CONSTRAINT facts_class_code_day_key UNIQUE (class_code, day);


--
-- Name: facts facts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facts
    ADD CONSTRAINT facts_pkey PRIMARY KEY (id);


--
-- Name: metrics metrics_code_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrics
    ADD CONSTRAINT metrics_code_version_key UNIQUE (code, version);


--
-- Name: metrics metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.metrics
    ADD CONSTRAINT metrics_pkey PRIMARY KEY (id);


--
-- Name: snapshots snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshots
    ADD CONSTRAINT snapshots_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: snapshots snapshots_baseline_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshots
    ADD CONSTRAINT snapshots_baseline_id_fkey FOREIGN KEY (baseline_id) REFERENCES public.snapshots(id);


--
-- Name: snapshots snapshots_metric_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.snapshots
    ADD CONSTRAINT snapshots_metric_id_fkey FOREIGN KEY (metric_id) REFERENCES public.metrics(id);


--
-- Name: monitor_configs / monitor_evaluations / monitor_alerts / monitor_events; Type: TABLE
-- 滚动监测：配置绑定口径版本与阈值；逐日评估冻结依据；预警与事件保留历史
--

CREATE TABLE public.monitor_configs (
    id integer NOT NULL,
    name character varying(100),
    metric_id integer NOT NULL,
    threshold double precision NOT NULL,
    start_date character varying(10) NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_by character varying(100) DEFAULT ''::character varying,
    created character varying(40),
    updated_by character varying(100) DEFAULT ''::character varying,
    updated character varying(40)
);

CREATE SEQUENCE public.monitor_configs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.monitor_configs_id_seq OWNED BY public.monitor_configs.id;

CREATE TABLE public.monitor_evaluations (
    id integer NOT NULL,
    monitor_id integer NOT NULL,
    eval_date character varying(10) NOT NULL,
    status character varying(20) NOT NULL,
    value double precision,
    numerator double precision,
    denominator double precision,
    threshold double precision NOT NULL,
    consecutive_below integer,
    revision integer,
    input_checksum character varying(64) NOT NULL,
    evidence json,
    error text DEFAULT ''::text,
    calculated character varying(40)
);

CREATE SEQUENCE public.monitor_evaluations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.monitor_evaluations_id_seq OWNED BY public.monitor_evaluations.id;

CREATE TABLE public.monitor_alerts (
    id integer NOT NULL,
    monitor_id integer NOT NULL,
    metric_id integer NOT NULL,
    anchor_date character varying(10) NOT NULL,
    trigger_date character varying(10) NOT NULL,
    start_date character varying(10),
    end_date character varying(10),
    status character varying(20) NOT NULL,
    threshold double precision NOT NULL,
    evidence json,
    confirmed_by character varying(100) DEFAULT ''::character varying,
    confirmed_at character varying(40) DEFAULT ''::character varying,
    confirmed_evidence json,
    revoked character varying(40) DEFAULT ''::character varying,
    revoke_reason text DEFAULT ''::text,
    created character varying(40),
    updated character varying(40)
);

CREATE SEQUENCE public.monitor_alerts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.monitor_alerts_id_seq OWNED BY public.monitor_alerts.id;

CREATE TABLE public.monitor_events (
    id integer NOT NULL,
    monitor_id integer NOT NULL,
    alert_id integer,
    action character varying(30) NOT NULL,
    actor character varying(100),
    detail json,
    created character varying(40)
);

CREATE SEQUENCE public.monitor_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.monitor_events_id_seq OWNED BY public.monitor_events.id;

ALTER TABLE ONLY public.monitor_configs ALTER COLUMN id SET DEFAULT nextval('public.monitor_configs_id_seq'::regclass);
ALTER TABLE ONLY public.monitor_evaluations ALTER COLUMN id SET DEFAULT nextval('public.monitor_evaluations_id_seq'::regclass);
ALTER TABLE ONLY public.monitor_alerts ALTER COLUMN id SET DEFAULT nextval('public.monitor_alerts_id_seq'::regclass);
ALTER TABLE ONLY public.monitor_events ALTER COLUMN id SET DEFAULT nextval('public.monitor_events_id_seq'::regclass);

ALTER TABLE ONLY public.monitor_configs
    ADD CONSTRAINT monitor_configs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.monitor_evaluations
    ADD CONSTRAINT monitor_evaluations_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.monitor_evaluations
    ADD CONSTRAINT monitor_evaluations_monitor_id_eval_date_key UNIQUE (monitor_id, eval_date);
ALTER TABLE ONLY public.monitor_alerts
    ADD CONSTRAINT monitor_alerts_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.monitor_events
    ADD CONSTRAINT monitor_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.monitor_configs
    ADD CONSTRAINT monitor_configs_metric_id_fkey FOREIGN KEY (metric_id) REFERENCES public.metrics(id);
ALTER TABLE ONLY public.monitor_evaluations
    ADD CONSTRAINT monitor_evaluations_monitor_id_fkey FOREIGN KEY (monitor_id) REFERENCES public.monitor_configs(id);
ALTER TABLE ONLY public.monitor_alerts
    ADD CONSTRAINT monitor_alerts_monitor_id_fkey FOREIGN KEY (monitor_id) REFERENCES public.monitor_configs(id);
ALTER TABLE ONLY public.monitor_alerts
    ADD CONSTRAINT monitor_alerts_metric_id_fkey FOREIGN KEY (metric_id) REFERENCES public.metrics(id);
ALTER TABLE ONLY public.monitor_events
    ADD CONSTRAINT monitor_events_monitor_id_fkey FOREIGN KEY (monitor_id) REFERENCES public.monitor_configs(id);
ALTER TABLE ONLY public.monitor_events
    ADD CONSTRAINT monitor_events_alert_id_fkey FOREIGN KEY (alert_id) REFERENCES public.monitor_alerts(id);


--
-- PostgreSQL database dump complete
--

\unrestrict szUMnyNRLyh6b3W1BvTghEYTthJm49RMYFenWPziQqHhQ5jWAPV312Charu96Ts

