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
