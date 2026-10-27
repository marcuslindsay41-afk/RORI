-- Additive PostgreSQL 15+ schema. Applied only by an explicitly selected admin.
CREATE SCHEMA rori_evidence;
REVOKE ALL ON SCHEMA rori_evidence FROM PUBLIC;
CREATE TABLE rori_evidence.schema_versions(version integer PRIMARY KEY, checksum text NOT NULL);
CREATE TABLE rori_evidence.principal_grants(
 login_role name NOT NULL, restaurant_id bigint NOT NULL CHECK(restaurant_id>0),
 actor_id text NOT NULL CHECK(actor_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
 capabilities text[] NOT NULL, PRIMARY KEY(login_role,restaurant_id)
);
CREATE FUNCTION rori_evidence.allowed(t bigint) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,rori_evidence AS $$
 SELECT EXISTS(SELECT 1 FROM rori_evidence.principal_grants WHERE login_role=session_user AND restaurant_id=t)
$$;
CREATE FUNCTION rori_evidence.actor(t bigint, capability text) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,rori_evidence AS $$
DECLARE result text;
BEGIN
 SELECT actor_id INTO result FROM rori_evidence.principal_grants
 WHERE login_role=session_user AND restaurant_id=t AND (capability='read' OR capability=ANY(capabilities));
 IF result IS NULL THEN RAISE EXCEPTION 'TENANT_OR_CAPABILITY_DENIED' USING ERRCODE='42501'; END IF;
 RETURN result;
END $$;
CREATE FUNCTION rori_evidence.lock_scope(t bigint) RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,rori_evidence AS $$
BEGIN
 PERFORM rori_evidence.actor(t,'read');
 IF current_setting('transaction_isolation') <> 'read committed' THEN
  RAISE EXCEPTION 'READ_COMMITTED_REQUIRED';
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('rori-evidence:'||t::text,0));
END $$;
CREATE TABLE rori_evidence.objects(
 restaurant_id bigint NOT NULL CHECK(restaurant_id>0), kind text NOT NULL,
 object_id uuid NOT NULL, revision integer NOT NULL CHECK(revision>0), previous_revision integer,
 payload jsonb NOT NULL, transport_digest text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(restaurant_id,kind,object_id,revision),
 FOREIGN KEY(restaurant_id,kind,object_id,previous_revision)
  REFERENCES rori_evidence.objects(restaurant_id,kind,object_id,revision),
 CHECK(kind IN ('evidence','verification','snapshot','assessment','eligibility','legacy_claim')),
 CHECK((payload->>'schema_version'='1.0.0') IS TRUE),
 CHECK((revision=1 AND previous_revision IS NULL) OR
       (kind IN ('evidence','verification') AND revision>1 AND previous_revision=revision-1)),
 CHECK(kind<>'eligibility' OR (payload->>'outcome'='deny') IS TRUE),
 CHECK(kind<>'assessment' OR (payload->>'decision_eligible'='false') IS TRUE),
 CHECK(kind<>'evidence' OR (payload->>'verification_status'='unverified') IS TRUE)
);
CREATE TABLE rori_evidence.links(
 restaurant_id bigint NOT NULL, parent_kind text NOT NULL, parent_id uuid NOT NULL, parent_revision integer NOT NULL,
 target_kind text NOT NULL, target_id uuid NOT NULL, target_revision integer NOT NULL,
 PRIMARY KEY(restaurant_id,parent_kind,parent_id,parent_revision,target_kind,target_id,target_revision),
 FOREIGN KEY(restaurant_id,parent_kind,parent_id,parent_revision)
  REFERENCES rori_evidence.objects(restaurant_id,kind,object_id,revision),
 FOREIGN KEY(restaurant_id,target_kind,target_id,target_revision)
  REFERENCES rori_evidence.objects(restaurant_id,kind,object_id,revision)
);
CREATE INDEX links_target_idx ON rori_evidence.links(restaurant_id,target_kind,target_id,target_revision);
CREATE TABLE rori_evidence.revocations(
 restaurant_id bigint NOT NULL, kind text NOT NULL, object_id uuid NOT NULL, revision integer NOT NULL,
 actor_id text NOT NULL, reason text NOT NULL CHECK(length(reason)>0), revoked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(restaurant_id,kind,object_id,revision),
 FOREIGN KEY(restaurant_id,kind,object_id,revision) REFERENCES rori_evidence.objects(restaurant_id,kind,object_id,revision)
);
CREATE TABLE rori_evidence.audit_heads(
 restaurant_id bigint PRIMARY KEY, stream_id uuid NOT NULL, sequence bigint NOT NULL, digest text
);
CREATE TABLE rori_evidence.audit_events(
 restaurant_id bigint NOT NULL, sequence bigint NOT NULL CHECK(sequence>0), event_id uuid NOT NULL UNIQUE,
 payload jsonb NOT NULL, digest text NOT NULL,
 PRIMARY KEY(restaurant_id,sequence), CHECK((payload->>'schema_version'='1.0.0') IS TRUE)
);
-- RLS is based on the authenticated database login, not a caller-set tenant GUC.
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['objects','links','revocations','audit_heads','audit_events'] LOOP
  EXECUTE format('ALTER TABLE rori_evidence.%I ENABLE ROW LEVEL SECURITY',tab);
  EXECUTE format('ALTER TABLE rori_evidence.%I FORCE ROW LEVEL SECURITY',tab);
  EXECUTE format('CREATE POLICY tenant_scope ON rori_evidence.%I USING (rori_evidence.allowed(restaurant_id)) WITH CHECK (rori_evidence.allowed(restaurant_id))',tab);
 END LOOP;
END $$;
CREATE FUNCTION rori_evidence.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'APPEND_ONLY_VIOLATION' USING ERRCODE='55000'; END $$;
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['objects','links','revocations','audit_events'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON rori_evidence.%I FOR EACH ROW EXECUTE FUNCTION rori_evidence.immutable()',tab);
  EXECUTE format('CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON rori_evidence.%I FOR EACH STATEMENT EXECUTE FUNCTION rori_evidence.immutable()',tab);
 END LOOP;
END $$;
CREATE FUNCTION rori_evidence.canonical(j jsonb) RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE result text;
BEGIN
 IF jsonb_typeof(j)='object' THEN
  SELECT '{'||coalesce(string_agg(to_jsonb(key)::text||':'||rori_evidence.canonical(value),',' ORDER BY key COLLATE "C"),'')||'}'
   INTO result FROM jsonb_each(j);
 ELSIF jsonb_typeof(j)='array' THEN
  SELECT '['||coalesce(string_agg(rori_evidence.canonical(value),',' ORDER BY ord),'')||']'
   INTO result FROM jsonb_array_elements(j) WITH ORDINALITY e(value,ord);
 ELSE result:=j::text; END IF;
 RETURN result;
END $$;
CREATE FUNCTION rori_evidence.emit_audit(t bigint,k text,i uuid,r integer,p jsonb,action_name text,reason_code text DEFAULT NULL)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,rori_evidence AS $$
DECLARE h rori_evidence.audit_heads%ROWTYPE; event jsonb; d text; eid uuid:=gen_random_uuid();
 stamp text; subject text; evidence jsonb:='[]'; snapshots jsonb:='[]'; vr jsonb:='null'; sid uuid:=i;
BEGIN
 INSERT INTO rori_evidence.audit_heads VALUES(t,gen_random_uuid(),0,NULL) ON CONFLICT DO NOTHING;
 SELECT * INTO h FROM rori_evidence.audit_heads WHERE restaurant_id=t FOR UPDATE;
 stamp:=to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US')||'+00:00';
 stamp:=replace(stamp,'.000000+00:00','+00:00');
 subject:=CASE k WHEN 'legacy_claim' THEN 'legacy_claim' WHEN 'verification' THEN 'verification' ELSE k END;
 IF k='evidence' THEN evidence:=jsonb_build_array(p->'reference'); END IF;
 IF k='snapshot' THEN snapshots:=jsonb_build_array(jsonb_build_object('restaurant_id',t,'snapshot_id',i,'digest',p->>'digest')); END IF;
 IF k='verification' THEN
  evidence:=jsonb_build_array(p->'evidence');
  vr:=jsonb_build_object('verification_id',i,'revision',r,'evidence',p->'evidence','issuer_id',p->>'issuer_id','purpose',p->>'purpose');
 END IF;
 event:=jsonb_build_object('schema_version','1.0.0','event_id',eid,'stream_id',h.stream_id,
  'sequence',h.sequence+1,'restaurant_id',t,'actor_id',rori_evidence.actor(t,'read'),'actor_kind','service',
  'action',action_name,'subject_type',subject,'subject_id',sid,'occurred_at',stamp,
  'evidence_refs',evidence,'snapshot_refs',snapshots,'verification_ref',vr,
  'reasons',CASE WHEN reason_code IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(reason_code) END,'previous_digest',h.digest);
 d:=encode(sha256(convert_to(rori_evidence.canonical(event),'UTF8')),'hex');
 event:=event||jsonb_build_object('digest',d);
 INSERT INTO rori_evidence.audit_events VALUES(t,h.sequence+1,eid,event,d);
 UPDATE rori_evidence.audit_heads SET sequence=h.sequence+1,digest=d WHERE restaurant_id=t;
END $$;
CREATE FUNCTION rori_evidence.bind(t bigint,k text,i uuid,r integer,tk text,ti uuid,tr integer,current_required boolean)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,rori_evidence AS $$
BEGIN
 IF current_required AND (EXISTS(SELECT 1 FROM rori_evidence.revocations WHERE restaurant_id=t AND kind=tk AND object_id=ti AND revision=tr)
  OR tr<>(SELECT max(revision) FROM rori_evidence.objects WHERE restaurant_id=t AND kind=tk AND object_id=ti)) THEN
  RAISE EXCEPTION 'STALE_OR_REVOKED_EVIDENCE';
 END IF;
 INSERT INTO rori_evidence.links VALUES(t,k,i,r,tk,ti,tr) ON CONFLICT DO NOTHING;
END $$;
CREATE FUNCTION rori_evidence.resolve_snapshot(t bigint,i uuid,d text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,rori_evidence AS $$
DECLARE result jsonb;
BEGIN
 PERFORM rori_evidence.lock_scope(t);
 SELECT payload INTO result FROM rori_evidence.objects WHERE restaurant_id=t AND kind='snapshot' AND object_id=i AND revision=1;
 IF result IS NULL OR result->>'digest' IS DISTINCT FROM d THEN RAISE EXCEPTION 'SNAPSHOT_BINDING_MISMATCH'; END IF;
 IF EXISTS(SELECT 1 FROM rori_evidence.revocations WHERE restaurant_id=t AND kind='snapshot' AND object_id=i AND revision=1)
 OR EXISTS(SELECT 1 FROM rori_evidence.links l WHERE l.restaurant_id=t AND l.parent_kind='snapshot' AND l.parent_id=i
 AND (EXISTS(SELECT 1 FROM rori_evidence.revocations x WHERE x.restaurant_id=t AND x.kind=l.target_kind AND x.object_id=l.target_id AND x.revision=l.target_revision)
 OR l.target_revision<>(SELECT max(o.revision) FROM rori_evidence.objects o WHERE o.restaurant_id=t AND o.kind=l.target_kind AND o.object_id=l.target_id)))
 THEN RAISE EXCEPTION 'STALE_OR_REVOKED_EVIDENCE'; END IF;
 RETURN result;
END $$;
CREATE FUNCTION rori_evidence.append_object(t bigint,k text,i uuid,r integer,p jsonb,expected_revision integer)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,rori_evidence AS $$
DECLARE head integer; actor_name text; ref jsonb; stored jsonb; target uuid; rev integer; capability text; expected_id text;
BEGIN
 PERFORM rori_evidence.lock_scope(t);
 capability:=CASE k WHEN 'verification' THEN 'verify:'||(p->>'purpose') WHEN 'assessment' THEN 'assess'
              WHEN 'eligibility' THEN 'evaluate' ELSE 'write' END;
 actor_name:=rori_evidence.actor(t,capability);
 IF p->>'schema_version' IS DISTINCT FROM '1.0.0' THEN RAISE EXCEPTION 'UNKNOWN_CONTRACT_VERSION'; END IF;
 IF (p->>CASE k WHEN 'evidence' THEN 'ingested_at' WHEN 'verification' THEN 'verified_at'
     WHEN 'snapshot' THEN 'created_at' WHEN 'assessment' THEN 'assessed_at'
     WHEN 'eligibility' THEN 'evaluated_at' WHEN 'legacy_claim' THEN 'ingested_at' END)::timestamptz
     > clock_timestamp() THEN RAISE EXCEPTION 'FUTURE_TIMESTAMP'; END IF;
 IF coalesce(p#>>'{scope,restaurant_id}',p#>>'{evidence,restaurant_id}',p->>'restaurant_id') IS DISTINCT FROM t::text THEN
  RAISE EXCEPTION 'TENANT_MISMATCH'; END IF;
 expected_id:=CASE k WHEN 'evidence' THEN p#>>'{reference,evidence_id}' WHEN 'verification' THEN p->>'verification_id'
 WHEN 'snapshot' THEN p->>'snapshot_id' WHEN 'assessment' THEN p->>'assessment_id' WHEN 'eligibility' THEN p->>'eligibility_id'
 WHEN 'legacy_claim' THEN p->>'claim_id' END;
 IF expected_id IS DISTINCT FROM i::text THEN RAISE EXCEPTION 'IDENTITY_MISMATCH'; END IF;
 IF k='evidence' AND ((p#>>'{reference,revision}')::int IS DISTINCT FROM r OR p#>>'{reference,restaurant_id}' IS DISTINCT FROM t::text) THEN RAISE EXCEPTION 'REVISION_MISMATCH'; END IF;
 IF k='verification' AND ((p->>'revision')::int IS DISTINCT FROM r OR p->>'issuer_id' IS DISTINCT FROM actor_name) THEN RAISE EXCEPTION 'VERIFIER_IDENTITY_MISMATCH'; END IF;
 IF k='assessment' AND p->>'assessor_id' IS DISTINCT FROM actor_name THEN RAISE EXCEPTION 'ASSESSOR_IDENTITY_MISMATCH'; END IF;
 IF k='eligibility' AND p->>'issuer_id' IS DISTINCT FROM actor_name THEN RAISE EXCEPTION 'ISSUER_IDENTITY_MISMATCH'; END IF;
 SELECT coalesce(max(revision),0) INTO head FROM rori_evidence.objects WHERE restaurant_id=t AND kind=k AND object_id=i;
 IF k='legacy_claim' AND head=1 THEN
  SELECT payload INTO stored FROM rori_evidence.objects WHERE restaurant_id=t AND kind=k AND object_id=i AND revision=1;
  IF stored->>'source_digest'=p->>'source_digest' THEN RETURN; END IF;
 END IF;
 IF head<>expected_revision OR r<>head+1 THEN RAISE EXCEPTION 'REVISION_CONFLICT' USING ERRCODE='40001'; END IF;
 IF k='evidence' AND r>1 AND (p#>>'{supersedes,evidence_id}' IS DISTINCT FROM i::text OR p#>>'{supersedes,restaurant_id}' IS DISTINCT FROM t::text OR (p#>>'{supersedes,revision}')::int IS DISTINCT FROM head) THEN RAISE EXCEPTION 'REVISION_MISMATCH'; END IF;
 INSERT INTO rori_evidence.objects VALUES(t,k,i,r,CASE WHEN r=1 THEN NULL ELSE head END,p,encode(sha256(convert_to(p::text,'UTF8')),'hex'),clock_timestamp());
 IF k='verification' THEN
  ref:=p->'evidence'; target:=(ref->>'evidence_id')::uuid; rev:=(ref->>'revision')::integer;
  SELECT payload INTO stored FROM rori_evidence.objects WHERE restaurant_id=t AND kind='evidence' AND object_id=target AND revision=rev;
  IF stored->>'kind'='legacy_claim' AND p->>'purpose'<>'import_integrity' THEN RAISE EXCEPTION 'LEGACY_CLAIM_NOT_OBSERVATION'; END IF;
  IF r>1 AND (SELECT payload->'evidence' FROM rori_evidence.objects WHERE restaurant_id=t AND kind=k AND object_id=i AND revision=head) IS DISTINCT FROM ref THEN RAISE EXCEPTION 'VERIFICATION_SCOPE_CHANGED'; END IF;
  PERFORM rori_evidence.bind(t,k,i,r,'evidence',target,rev,true);
 ELSIF k='snapshot' THEN
  FOR ref IN SELECT value FROM jsonb_array_elements(p->'records') LOOP
   target:=(ref#>>'{reference,evidence_id}')::uuid; rev:=(ref#>>'{reference,revision}')::integer;
   SELECT payload INTO stored FROM rori_evidence.objects WHERE restaurant_id=t AND kind='evidence' AND object_id=target AND revision=rev;
   IF stored IS DISTINCT FROM ref THEN RAISE EXCEPTION 'SNAPSHOT_CONTENT_MISMATCH'; END IF;
   PERFORM rori_evidence.bind(t,k,i,r,'evidence',target,rev,true);
  END LOOP;
  FOR ref IN SELECT value FROM jsonb_array_elements(p->'verification_refs') LOOP
   target:=(ref->>'verification_id')::uuid; rev:=(ref->>'revision')::integer;
   SELECT payload INTO stored FROM rori_evidence.objects WHERE restaurant_id=t AND kind='verification' AND object_id=target AND revision=rev;
   IF stored IS NULL OR stored->>'status' IS DISTINCT FROM 'verified' OR stored->'evidence' IS DISTINCT FROM ref->'evidence'
    OR stored->>'issuer_id' IS DISTINCT FROM ref->>'issuer_id' OR stored->>'purpose' IS DISTINCT FROM ref->>'purpose' THEN RAISE EXCEPTION 'VERIFICATION_BINDING_MISMATCH'; END IF;
   PERFORM rori_evidence.bind(t,k,i,r,'verification',target,rev,true);
  END LOOP;
 ELSIF k IN ('assessment','eligibility') THEN
  FOR ref IN SELECT value FROM jsonb_array_elements(p->'snapshots') LOOP
   target:=(ref->>'snapshot_id')::uuid;
   IF ref->>'restaurant_id' IS DISTINCT FROM t::text THEN RAISE EXCEPTION 'TENANT_MISMATCH'; END IF;
   SELECT payload INTO stored FROM rori_evidence.objects WHERE restaurant_id=t AND kind='snapshot' AND object_id=target AND revision=1;
   IF stored->>'digest' IS DISTINCT FROM ref->>'digest' THEN RAISE EXCEPTION 'SNAPSHOT_BINDING_MISMATCH'; END IF;
   PERFORM rori_evidence.bind(t,k,i,r,'snapshot',target,1,false);
  END LOOP;
  IF k='eligibility' THEN
   FOR ref IN SELECT value FROM jsonb_array_elements(p->'assessments') LOOP
    IF ref->>'restaurant_id' IS DISTINCT FROM t::text THEN RAISE EXCEPTION 'TENANT_MISMATCH'; END IF;
    target:=(ref->>'assessment_id')::uuid;
    SELECT payload INTO stored FROM rori_evidence.objects WHERE restaurant_id=t AND kind='assessment' AND object_id=target AND revision=1;
    IF stored->'snapshots' IS DISTINCT FROM ref->'snapshots' OR stored->'policy' IS DISTINCT FROM ref->'policy' THEN RAISE EXCEPTION 'ASSESSMENT_BINDING_MISMATCH'; END IF;
    PERFORM rori_evidence.bind(t,k,i,r,'assessment',target,1,false);
   END LOOP;
  END IF;
 END IF;
 PERFORM rori_evidence.emit_audit(t,k,i,r,p,CASE k WHEN 'verification' THEN 'verify' WHEN 'assessment' THEN 'assess' WHEN 'eligibility' THEN 'deny' ELSE CASE WHEN r>1 THEN 'correct' ELSE 'submit' END END,
  CASE WHEN k='eligibility' THEN 'policy_unavailable' ELSE NULL END);
END $$;
CREATE FUNCTION rori_evidence.revoke_object(t bigint,k text,i uuid,r integer,reason_code text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,rori_evidence AS $$
DECLARE p jsonb;
BEGIN
 PERFORM rori_evidence.lock_scope(t);
 PERFORM rori_evidence.actor(t,'revoke');
 IF reason_code NOT IN ('revoked_evidence','revision_mismatch','invalid_quantity','contradictory_variance') THEN RAISE EXCEPTION 'INVALID_REASON'; END IF;
 SELECT payload INTO p FROM rori_evidence.objects WHERE restaurant_id=t AND kind=k AND object_id=i AND revision=r;
 IF p IS NULL THEN RAISE EXCEPTION 'MISSING_EVIDENCE'; END IF;
 IF EXISTS(SELECT 1 FROM rori_evidence.revocations WHERE restaurant_id=t AND kind=k AND object_id=i AND revision=r) THEN RETURN; END IF;
 INSERT INTO rori_evidence.revocations VALUES(t,k,i,r,rori_evidence.actor(t,'read'),reason_code,clock_timestamp());
 PERFORM rori_evidence.emit_audit(t,k,i,r,p,'revoke',reason_code);
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA rori_evidence FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA rori_evidence FROM PUBLIC;
