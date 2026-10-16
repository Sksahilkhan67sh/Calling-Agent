from scripts.check_api_contract import compare, normalise_path


def _doc(paths):
    return {"paths": paths}


def op(params=(), codes=("200",)):
    return {"parameters": list(params), "responses": {c: {} for c in codes}}


def p(name, where="query"):
    return {"name": name, "in": where}


def test_normalise_path():
    assert normalise_path("/v1/campaigns/{campaign_id}") == "/campaigns/{}"
    assert normalise_path("/campaigns/{id}/start") == "/campaigns/{}/start"


def test_unimplemented_is_informational():
    spec = _doc({"/campaigns": {"get": op()}, "/contacts": {"post": op()}})
    report = compare(spec, _doc({}))
    assert report.exit_code == 0 and len(report.not_implemented) == 2 and report.drift == []


def test_matching_implementation_has_no_drift():
    spec = _doc({"/campaigns/{id}": {"get": op([p("id", "path"), p("page")], ["200", "404"])}})
    impl = _doc({"/v1/campaigns/{pk}": {"get": op([p("pk", "path"), p("page")], ["200", "404", "429"])}})
    report = compare(spec, impl)
    assert report.drift == []
    assert report.compared == 1


def test_parameter_drift_fails():
    spec = _doc({"/campaigns": {"get": op([p("status")])}})
    impl = _doc({"/campaigns": {"get": op([p("state")])}})
    assert compare(spec, impl).exit_code == 1


def test_missing_response_code_fails():
    spec = _doc({"/campaigns": {"get": op(codes=["200", "403"])}})
    impl = _doc({"/campaigns": {"get": op(codes=["200"])}})
    report = compare(spec, impl)
    assert report.exit_code == 1 and "403" in report.drift[0]


def test_missing_method_on_implemented_path_fails():
    spec = _doc({"/campaigns": {"get": op(), "post": op()}})
    impl = _doc({"/campaigns": {"get": op()}})
    assert any("POST /campaigns" in d for d in compare(spec, impl).drift)


def test_undocumented_implemented_path_fails():
    report = compare(_doc({}), _doc({"/secret": {"get": op()}}))
    assert report.exit_code == 1


def test_internal_paths_ignored_and_refs_resolved():
    spec = {
        "paths": {
            "/a": {
                "get": {"parameters": [{"$ref": "#/components/parameters/Page"}], "responses": {"200": {}}}
            }
        },
        "components": {"parameters": {"Page": p("page")}},
    }
    impl = _doc({"/a": {"get": op([p("page")])}, "/healthz": {"get": op()}})
    report = compare(spec, impl)
    assert report.drift == [] and report.internal == ["GET /healthz"]


def test_documented_proposed_additions_are_informational():
    impl = _doc(
        {
            "/auth/csrf": {"get": op(codes=("204",))},
            "/auth/me": {"get": op(codes=("200", "401"))},
            "/auth/mfa/enroll": {"post": op()},
            "/auth/mfa/confirm": {"post": op()},
        }
    )
    report = compare(_doc({}), impl)
    assert report.exit_code == 0 and report.drift == []
    assert report.proposed_additions == [
        "GET /auth/csrf",
        "GET /auth/me",
        "POST /auth/mfa/confirm",
        "POST /auth/mfa/enroll",
    ]


def test_undocumented_auth_path_next_to_proposed_additions_still_fails():
    impl = _doc({"/auth/csrf": {"get": op()}, "/auth/backdoor": {"post": op()}})
    report = compare(_doc({}), impl)
    assert report.exit_code == 1
    assert report.drift == ["POST /auth/backdoor: implemented but not defined in the contract"]
    assert report.proposed_additions == ["GET /auth/csrf"]


def test_proposed_addition_wrong_method_still_fails():
    report = compare(_doc({}), _doc({"/auth/csrf": {"post": op()}}))
    assert report.exit_code == 1 and report.proposed_additions == []


def test_once_the_contract_defines_a_proposed_addition_it_is_compared_normally():
    spec = _doc({"/auth/csrf": {"get": op(codes=("204",))}})
    impl = _doc({"/auth/csrf": {"get": op(codes=("200",))}})
    report = compare(spec, impl)
    assert report.proposed_additions == []
    assert any("response codes missing" in d for d in report.drift)
