-- Additive only. Does not replace 001 or relax any deny-only object constraint.
CREATE TABLE rori_evidence.inventory_profiles(
 restaurant_id bigint NOT NULL CHECK(restaurant_id>0), identifier text NOT NULL,
 version text NOT NULL, digest text NOT NULL CHECK(digest ~ '^[0-9a-f]{64}$'),
 payload jsonb NOT NULL CHECK((payload->>'schema_version'='1.0.0') IS TRUE),
 provisioned_by name NOT NULL DEFAULT session_user, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(restaurant_id,identifier,version)
);
CREATE TABLE rori_evidence.inventory_manifests(
 restaurant_id bigint NOT NULL CHECK(restaurant_id>0), manifest_id uuid NOT NULL,
 digest text NOT NULL CHECK(digest ~ '^[0-9a-f]{64}$'), payload jsonb NOT NULL,
 PRIMARY KEY(restaurant_id,manifest_id)
);
CREATE TABLE rori_evidence.assessment_runs(
 restaurant_id bigint NOT NULL CHECK(restaurant_id>0), idempotency_key text NOT NULL,
 request_digest text NOT NULL CHECK(request_digest ~ '^[0-9a-f]{64}$'),
 assessment_id uuid NOT NULL, assessment_kind text NOT NULL DEFAULT 'assessment' CHECK(assessment_kind='assessment'),
 assessment_revision integer NOT NULL DEFAULT 1 CHECK(assessment_revision=1), receipt jsonb NOT NULL,
 PRIMARY KEY(restaurant_id,idempotency_key), UNIQUE(restaurant_id,assessment_id),
 FOREIGN KEY(restaurant_id,assessment_kind,assessment_id,assessment_revision)
 REFERENCES rori_evidence.objects(restaurant_id,kind,object_id,revision)
);
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['inventory_profiles','inventory_manifests','assessment_runs'] LOOP
  EXECUTE format('ALTER TABLE rori_evidence.%I ENABLE ROW LEVEL SECURITY',tab);
  EXECUTE format('ALTER TABLE rori_evidence.%I FORCE ROW LEVEL SECURITY',tab);
  EXECUTE format('CREATE POLICY tenant_scope ON rori_evidence.%I USING (rori_evidence.allowed(restaurant_id)) WITH CHECK (rori_evidence.allowed(restaurant_id))',tab);
  EXECUTE format('CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON rori_evidence.%I FOR EACH ROW EXECUTE FUNCTION rori_evidence.immutable()',tab);
  EXECUTE format('CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON rori_evidence.%I FOR EACH STATEMENT EXECUTE FUNCTION rori_evidence.immutable()',tab);
 END LOOP;
END $$;
CREATE FUNCTION rori_evidence.assessment_context(t bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,rori_evidence AS $$
DECLARE a text;
BEGIN
 PERFORM rori_evidence.lock_scope(t);
 a:=rori_evidence.actor(t,'assess');
 PERFORM 1 FROM rori_evidence.principal_grants WHERE restaurant_id=t AND login_role=session_user FOR SHARE;
 RETURN jsonb_build_object('actor',a,'now',clock_timestamp(),'database',current_database());
END $$;
CREATE FUNCTION rori_evidence.current_verification(t bigint,i uuid,r integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,rori_evidence AS $$
DECLARE v jsonb; ei uuid; er integer;
BEGIN
 PERFORM rori_evidence.lock_scope(t);
 PERFORM rori_evidence.actor(t,'assess');
 SELECT payload INTO v FROM rori_evidence.objects WHERE restaurant_id=t AND kind='verification' AND object_id=i AND revision=r;
 IF v IS NULL THEN RAISE EXCEPTION 'MISSING_VERIFICATION'; END IF;
 IF jsonb_typeof(v->'supporting_refs') IS DISTINCT FROM 'array' OR
    jsonb_array_length(v->'supporting_refs')=0 OR v->>'method' IS NULL OR v->>'verified_at' IS NULL
 THEN RAISE EXCEPTION 'VERIFICATION_PAYLOAD_INVALID'; END IF;
 IF v->>'status' IS DISTINCT FROM 'verified' THEN RAISE EXCEPTION 'VERIFICATION_NOT_VERIFIED'; END IF;
 IF EXISTS(SELECT 1 FROM rori_evidence.revocations WHERE restaurant_id=t AND kind='verification' AND object_id=i AND revision=r)
 OR r<>(SELECT max(revision) FROM rori_evidence.objects WHERE restaurant_id=t AND kind='verification' AND object_id=i)
 THEN RAISE EXCEPTION 'STALE_OR_REVOKED_VERIFICATION'; END IF;
 PERFORM 1 FROM rori_evidence.principal_grants WHERE restaurant_id=t AND actor_id=v->>'issuer_id'
   AND ('verify:'||(v->>'purpose'))=ANY(capabilities) FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'VERIFIER_AUTHORITY_UNAVAILABLE' USING ERRCODE='42501'; END IF;
 ei:=(v#>>'{evidence,evidence_id}')::uuid; er:=(v#>>'{evidence,revision}')::integer;
 IF EXISTS(SELECT 1 FROM rori_evidence.revocations WHERE restaurant_id=t AND kind='evidence' AND object_id=ei AND revision=er)
 OR er IS DISTINCT FROM (SELECT max(revision) FROM rori_evidence.objects WHERE restaurant_id=t AND kind='evidence' AND object_id=ei)
 THEN RAISE EXCEPTION 'STALE_OR_REVOKED_EVIDENCE'; END IF;
 RETURN v;
END $$;
CREATE FUNCTION rori_evidence.put_inventory_manifest(t bigint,p jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,rori_evidence AS $$
DECLARE i uuid; previous jsonb;
BEGIN
 PERFORM rori_evidence.lock_scope(t); PERFORM rori_evidence.actor(t,'write');
 IF p->>'schema_version' IS DISTINCT FROM '1.0.0' OR p#>>'{scope,restaurant_id}' IS DISTINCT FROM t::text
 OR p#>>'{snapshot,restaurant_id}' IS DISTINCT FROM t::text OR p->>'digest' IS NULL THEN RAISE EXCEPTION 'MANIFEST_BINDING_INVALID'; END IF;
 i:=(p->>'manifest_id')::uuid;
 PERFORM rori_evidence.resolve_snapshot(t,(p#>>'{snapshot,snapshot_id}')::uuid,p#>>'{snapshot,digest}');
 SELECT payload INTO previous FROM rori_evidence.inventory_manifests WHERE restaurant_id=t AND manifest_id=i;
 IF previous IS NOT NULL THEN
  IF previous IS DISTINCT FROM p THEN RAISE EXCEPTION 'MANIFEST_CONFLICT'; END IF;
  RETURN;
 END IF;
 INSERT INTO rori_evidence.inventory_manifests VALUES(t,i,p->>'digest',p);
 PERFORM rori_evidence.emit_audit(t,'inventory_manifest',i,1,p,'submit');
END $$;
CREATE FUNCTION rori_evidence.save_assessment_run(t bigint,k text,d text,p jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,rori_evidence AS $$
DECLARE a jsonb; i uuid; existing rori_evidence.assessment_runs%ROWTYPE;
BEGIN
 PERFORM rori_evidence.lock_scope(t); PERFORM rori_evidence.actor(t,'assess');
 IF k IS NULL OR k !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$' THEN RAISE EXCEPTION 'INVALID_IDEMPOTENCY_KEY'; END IF;
 i:=(p#>>'{assessment,assessment_id}')::uuid;
 SELECT payload INTO a FROM rori_evidence.objects WHERE restaurant_id=t AND kind='assessment' AND object_id=i AND revision=1;
 IF a IS NULL OR a IS DISTINCT FROM p->'assessment' OR a->>'decision_eligible' IS DISTINCT FROM 'false'
 OR p#>>'{provenance,request,scope,restaurant_id}' IS DISTINCT FROM t::text
 THEN RAISE EXCEPTION 'ASSESSMENT_RECEIPT_BINDING_INVALID'; END IF;
 SELECT * INTO existing FROM rori_evidence.assessment_runs WHERE restaurant_id=t AND idempotency_key=k;
 IF FOUND THEN
  IF existing.request_digest IS DISTINCT FROM d OR existing.receipt IS DISTINCT FROM p THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
  RETURN;
 END IF;
 INSERT INTO rori_evidence.assessment_runs(restaurant_id,idempotency_key,request_digest,assessment_id,receipt) VALUES(t,k,d,i,p);
 PERFORM rori_evidence.emit_audit(t,'assessment_run',i,1,p,'assess');
END $$;
REVOKE ALL ON rori_evidence.inventory_profiles,rori_evidence.inventory_manifests,rori_evidence.assessment_runs FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION rori_evidence.assessment_context(bigint),rori_evidence.current_verification(bigint,uuid,integer),rori_evidence.put_inventory_manifest(bigint,jsonb),rori_evidence.save_assessment_run(bigint,text,text,jsonb) FROM PUBLIC;
